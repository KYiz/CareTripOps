import asyncio
import hashlib
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from app.config import settings
from app.db import (
    Approval, AuditEvent, Case, Evidence, Offer, OfferAssessment, Order,
    Requirement, SessionLocal, add_event, engine, set_status,
)
from app.graph import build_graph
from app.skills.effects import decide_approval, demo_nonce
from app.skills.destinations import resolve_destination
from app.skills.contracts import DraftPlanInput, RequirementInput
from app.skills.domain import build_draft_itinerary, extract_requirements, normalize_currency
from app.skills.destinations import resolve_attractions
from app.skills.model_adapter import extract_requirements_live
from app.two_brains import planning_enabled
from app.guide import (build_revision_graph, confirm_revision, guide_answer, guide_context,
                       new_proposal_id, select_attraction, classify_intent, record_guide_turn)


def envelope(data):
    return {"data": data, "request_id": str(uuid4())}


def iso(value):
    return value.isoformat() if value else None


def money(value):
    return f"{Decimal(value):.2f}" if value is not None else None


def fail(code: str, message: str, status: int = 409):
    raise HTTPException(status_code=status, detail={"code": code, "message": message, "retryable": False})


async def drive(app: FastAPI, case_id: str, resume: bool = False):
    config = {"configurable": {"thread_id": case_id}}
    try:
        await app.state.graph.ainvoke(Command(resume=True) if resume else {"case_id": case_id}, config=config)
    except Exception as exc:
        with SessionLocal.begin() as session:
            case = session.get(Case, case_id, with_for_update=True)
            if case and case.status not in {"DEMO_COMPLETED", "REJECTED", "HUMAN_REVIEW"}:
                set_status(session, case, "RECOVERY_REQUIRED", "runner", "Manager", "RUN_FAILED",
                           {"error_type": type(exc).__name__})
    finally:
        app.state.tasks.pop(case_id, None)


def launch(app: FastAPI, case_id: str, resume: bool = False):
    if case_id in app.state.tasks:
        return
    app.state.tasks[case_id] = asyncio.create_task(drive(app, case_id, resume))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.model_mode not in {"mock_llm", "api"}:
        raise RuntimeError("MODEL_MODE must be mock_llm or api")
    if settings.llm_provider not in {"openai", "gemini"}:
        raise RuntimeError("LLM_PROVIDER must be openai or gemini")
    app.state.tasks = {}
    db_dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    async with AsyncPostgresSaver.from_conn_string(db_dsn) as checkpointer:
        await checkpointer.setup()
        app.state.graph = build_graph(checkpointer)
        app.state.revision_graph = build_revision_graph(checkpointer)
        with SessionLocal.begin() as session:
            interrupted = session.scalars(select(Case).where(Case.status.in_([
                "RECEIVED", "REQUIREMENTS_READY", "OFFERS_DISCOVERED", "EVIDENCE_REVIEW",
                "EVIDENCE_CONFLICT", "OFFERS_VERIFIED", "APPROVED", "MOCK_BOOKING",
            ]))).all()
            for case in interrupted:
                set_status(session, case, "RECOVERY_REQUIRED", "startup", "Manager", "STARTUP_RECOVERY_REQUIRED", {})
        yield
        for task in list(app.state.tasks.values()):
            task.cancel()
        if app.state.tasks:
            await asyncio.gather(*app.state.tasks.values(), return_exceptions=True)


app = FastAPI(title="CareTrip Ops V4.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")


def valid_case_token(case_id: str, token: str | None) -> bool:
    if not token:
        return False
    with SessionLocal() as session:
        case = session.get(Case, case_id)
        return bool(case and case.access_token_hash and secrets.compare_digest(
            case.access_token_hash, hashlib.sha256(token.encode()).hexdigest()))


def voice_origin_allowed(origin: str, host: str) -> bool:
    """Allow configured demo origins and the exact host serving the same-origin UI."""
    if origin in {settings.frontend_origin, "http://localhost:8080", "http://127.0.0.1:8080"}:
        return True
    parsed = urlsplit(origin)
    return bool(host and parsed.scheme in {"http", "https"}
                and parsed.netloc.lower() == host.lower()
                and origin == f"{parsed.scheme}://{parsed.netloc}")


@app.middleware("http")
async def case_access(request: Request, call_next):
    match = re.fullmatch(r"/api/cases/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?:/.*)?", request.url.path)
    if match and not await run_in_threadpool(valid_case_token, match.group(1),
                                              request.headers.get("X-Case-Token")):
        return JSONResponse(status_code=403, content={"error": {
            "code": "CASE_ACCESS_DENIED", "message": "Case access token is missing or invalid",
            "retryable": False}, "request_id": str(uuid4())})
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail), "retryable": False}
    return JSONResponse(status_code=exc.status_code, content={"error": detail, "request_id": str(uuid4())})


class CreateCase(BaseModel):
    request: str = Field(min_length=8)
    demo_actor: str = "demo-user"
    demo_date: date | None = None
    voice_draft: bool = False


class Clarification(BaseModel):
    answers: dict[str, str | int | float]


class Decision(BaseModel):
    decision: str
    nonce: str
    expected_state_version: int


class GuideSelection(BaseModel):
    attraction: str = Field(min_length=1, max_length=120)


class GuideMessage(BaseModel):
    message: str = Field(min_length=2, max_length=1000)


class RevisionRequest(BaseModel):
    request: str = Field(min_length=5, max_length=500)


class RevisionDecision(BaseModel):
    proposal_id: str
    accept: bool


@app.get("/api/guide/capabilities")
def guide_capabilities():
    import os
    return envelope({"voice_available": bool(os.getenv("GEMINI_API_KEY")),
                     "voice_provider": "Gemini Live" if os.getenv("GEMINI_API_KEY") else None})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
@app.get("/api/readyz")
def readyz():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        fail("DB_UNAVAILABLE", "Database is unavailable", 503)
    return {"status": "ready", "model_mode": settings.model_mode,
            "llm_provider": settings.llm_provider if settings.model_mode == "api" else None}


@app.post("/api/cases", status_code=201)
async def create_case(body: CreateCase, request: Request):
    if body.demo_actor != "demo-user":
        fail("INVALID_ACTOR", "Only the labeled demo actor is supported", 400)
    required_key = "GEMINI_API_KEY" if settings.llm_provider == "gemini" else "OPENAI_API_KEY"
    if settings.model_mode == "api" and not os.getenv(required_key):
        fail("MODEL_UNAVAILABLE", f"Live model mode requires {required_key}", 503)
    access_token = secrets.token_urlsafe(32)
    with SessionLocal.begin() as session:
        case_id = str(uuid4())
        case = Case(id=case_id, thread_id=case_id, access_token_hash=hashlib.sha256(access_token.encode()).hexdigest(),
                    original_request=body.request, demo_date=body.demo_date,
                    guide_state={"requirements_model_mode": settings.model_mode,
                                 "requirements_provider": settings.llm_provider if settings.model_mode == "api" else None,
                                 "voice_draft": body.voice_draft})
        session.add(case)
        session.flush()
        add_event(session, case.id, "Manager", "CASE_CREATED", "RECEIVED",
                  {"model_mode": settings.model_mode,
                   "llm_provider": settings.llm_provider if settings.model_mode == "api" else None})
    launch(request.app, case_id)
    return envelope({"case_id": case_id, "thread_id": case_id, "status": "RECEIVED",
                     "access_token": access_token})


def get_case_or_404(session, case_id: str):
    case = session.get(Case, case_id)
    if not case:
        fail("CASE_NOT_FOUND", "Case not found", 404)
    return case


@app.get("/api/cases/{case_id}")
def read_case(case_id: str):
    with SessionLocal() as session:
        case = get_case_or_404(session, case_id)
        req = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
        requirements = None if not req else {
            "destination": req.destination, "departure_date": iso(req.departure_date),
            "destination_scope": req.destination_scope, "attractions": req.attractions,
            "travel_pace": req.travel_pace,
            "traveler_count": req.traveler_count, "duration_days": req.duration_days,
            "budget": money(req.budget), "currency": req.currency,
            "hard_constraints": req.hard_constraints, "missing_fields": req.missing_fields,
        }
        draft_itinerary = [] if not req else [day.model_dump() for day in build_draft_itinerary(DraftPlanInput(
            destination=req.destination, destination_scope=req.destination_scope,
            duration_days=req.duration_days, attractions=req.attractions, travel_pace=req.travel_pace))]
        guide_state = case.guide_state or {}
        draft_itinerary = guide_state.get("accepted_days") or guide_state.get("initial_days") or draft_itinerary
        itinerary_source = guide_state.get("itinerary_source", "DETERMINISTIC_DRAFT")
        if (req and not req.missing_fields and not guide_state.get("initial_days")
                and planning_enabled() and case.status not in {"HUMAN_REVIEW", "RECOVERY_REQUIRED", "REJECTED"}):
            draft_itinerary, itinerary_source = [], "PENDING"
        mode = (case.guide_state or {}).get("requirements_model_mode", settings.model_mode)
        model_events = set(session.scalars(select(AuditEvent.event_type).where(
            AuditEvent.case_id == case_id,
            AuditEvent.event_type.in_(["MODEL_USAGE", "MODEL_ERROR", "MODEL_CALL_LIMIT"]))).all())
        model_status = ("MOCK" if mode == "mock_llm" else "FAILED" if "MODEL_ERROR" in model_events
                        or "MODEL_CALL_LIMIT" in model_events else "SUCCEEDED" if "MODEL_USAGE" in model_events
                        else "PENDING")
        return envelope({"case_id": case.id, "status": case.status, "active_node": case.active_node,
                         "state_version": case.state_version, "requirements": requirements,
                         "draft_itinerary": draft_itinerary,
                         "itinerary_source": itinerary_source,
                         "itinerary_version": guide_state.get("itinerary_version", 0),
                         "missing_fields": req.missing_fields if req else [],
                         "next_action": "CLARIFY" if case.status == "NEEDS_CLARIFICATION" else
                         "DECIDE" if case.status == "AWAITING_APPROVAL" else None,
                         "model_mode": mode, "model_status": model_status,
                         "llm_provider": (case.guide_state or {}).get("requirements_provider"),
                         "created_at": iso(case.created_at)})


def apply_clarification(case_id: str, answers: dict, app_instance: FastAPI):
    allowed = {"destination", "departure_date", "traveler_count", "duration_days", "budget", "currency"}
    if not answers or not set(answers).issubset(allowed):
        fail("INVALID_CLARIFICATION", "Unsupported clarification fields", 400)
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        if not case or case.status != "NEEDS_CLARIFICATION" or case_id in app_instance.state.tasks:
            fail("INVALID_STATE", "Case is not waiting for clarification")
        if case.clarification_count >= settings.max_clarifications:
            fail("CLARIFICATION_LIMIT", "Clarification limit reached", 429)
        req = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
        for key, value in answers.items():
            try:
                if key == "departure_date":
                    value = date.fromisoformat(str(value))
                elif key in {"traveler_count", "duration_days"}:
                    value = int(value)
                    if value < 1:
                        raise ValueError()
                elif key == "budget":
                    value = Decimal(str(value))
                    if value <= 0:
                        raise ValueError()
                elif key == "currency":
                    value = normalize_currency(str(value))
                    if value != "NZD":
                        fail("INVALID_CURRENCY", "This New Zealand demo requires NZD", 422)
                else:
                    value = str(value).strip()
            except (ValueError, InvalidOperation, TypeError):
                fail("INVALID_CLARIFICATION", f"Invalid value for {key}", 400)
            setattr(req, key, value)
            if key == "destination":
                canonical, scope = resolve_destination(str(value))
                if scope == "OUTSIDE_NZ":
                    fail("DESTINATION_OUTSIDE_NZ", "This demo currently supports travel within New Zealand only", 422)
                req.destination = canonical
                req.destination_scope = scope
        case.clarification_count += 1
        add_event(session, case.id, "Requirements Worker", "CLARIFICATION_RECEIVED", case.status,
                  {"fields": list(answers)})
    launch(app_instance, case_id, resume=True)
    return {"case_id": case_id, "accepted": True}


async def collect_spoken_clarification(case_id: str, message: str, app_instance: FastAPI) -> dict | None:
    with SessionLocal() as session:
        case = session.get(Case, case_id)
        if not case or case.status != "NEEDS_CLARIFICATION":
            return None
        req = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
        missing = list(req.missing_fields)
        existing = dict((case.guide_state or {}).get("spoken_answers", {}))
        voice_draft = bool((case.guide_state or {}).get("voice_draft"))
        conversation = list((case.guide_state or {}).get("conversation", []))
        demo_date = case.demo_date
    parsed = extract_requirements(RequirementInput(request=message.ljust(8), demo_date=demo_date))
    if parsed.destination_scope == "OUTSIDE_NZ":
        return {"saved": False, "error": "This demo supports New Zealand destinations only."}
    for field in missing:
        value = getattr(parsed, field, None)
        if value is not None:
            existing[field] = str(value) if field in {"budget", "departure_date"} else value
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        case.guide_state = {**(case.guide_state or {}), "spoken_answers": existing}
        add_event(session, case_id, "Requirements Worker", "CLARIFICATION_DRAFTED", case.status,
                  {"fields": sorted(existing)})
    remaining = [field for field in missing if field not in existing]
    if remaining:
        return {"saved": False, "remaining": remaining}
    if voice_draft and settings.model_mode == "api":
        full_request = " ".join(item["text"] for item in conversation if item["role"] == "traveler")
        with SessionLocal.begin() as session:
            case = session.get(Case, case_id, with_for_update=True)
            if case.llm_calls >= settings.max_llm_calls:
                return {"saved": False, "error": "The model call limit was reached. Please use the text form."}
            case.llm_calls += 1
            add_event(session, case_id, "Requirements Worker", "MODEL_CALL_STARTED", case.status,
                      {"role": "voice_requirements", "call_number": case.llm_calls})
        try:
            model_result, usage = await asyncio.to_thread(
                extract_requirements_live,
                RequirementInput(request=full_request.ljust(8), demo_date=demo_date),
            )
        except Exception as exc:
            with SessionLocal.begin() as session:
                case = session.get(Case, case_id)
                add_event(session, case_id, "Requirements Worker", "MODEL_ERROR", case.status,
                          {"role": "voice_requirements", "error_type": type(exc).__name__})
            return {"saved": False, "error": "Gemini could not validate the spoken details. Please retry or use text."}
        if model_result.destination_scope == "OUTSIDE_NZ":
            return {"saved": False, "error": "This demo supports New Zealand destinations only."}
        if model_result.destination and existing.get("destination") and model_result.destination != existing["destination"]:
            return {"saved": False, "error": "I heard different destinations. Please confirm one destination in text."}
        with SessionLocal.begin() as session:
            case = session.get(Case, case_id, with_for_update=True)
            req = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
            req.attractions = resolve_attractions(full_request, existing.get("destination"))
            req.travel_pace = extract_requirements(RequirementInput(request=full_request.ljust(8))).travel_pace
            req.hard_constraints = {"elevator_required": model_result.elevator_required}
            case.original_request = full_request
            case.guide_state = {**(case.guide_state or {}), "voice_draft": False}
            add_event(session, case_id, "Requirements Worker", "MODEL_USAGE", case.status,
                      {key: value for key, value in usage.items() if value is not None})
    apply_clarification(case_id, {field: existing[field] for field in missing}, app_instance)
    return {"saved": True, "fields": missing}


@app.post("/api/cases/{case_id}/clarifications")
async def clarify(case_id: str, body: Clarification, request: Request):
    result = apply_clarification(case_id, body.answers, request.app)
    return envelope(result)


@app.get("/api/cases/{case_id}/guide")
def read_guide(case_id: str):
    try:
        return envelope(guide_context(case_id))
    except LookupError:
        fail("CASE_NOT_FOUND", "Case not found", 404)


@app.post("/api/cases/{case_id}/guide/attraction")
def update_guide_attraction(case_id: str, body: GuideSelection):
    try:
        return envelope(select_attraction(case_id, body.attraction))
    except LookupError:
        fail("CASE_NOT_FOUND", "Case not found", 404)
    except ValueError as exc:
        fail("INVALID_ATTRACTION", str(exc), 422)


@app.post("/api/cases/{case_id}/guide/messages")
async def guide_message(case_id: str, body: GuideMessage, request: Request):
    try:
        context = guide_context(case_id)
        record_guide_turn(case_id, "traveler", body.message, "text")
        clarification = await collect_spoken_clarification(case_id, body.message, request.app)
        if clarification:
            reply = ("I saved those details and am continuing your trip plan." if clarification.get("saved") else
                     clarification.get("error") or "Thank you. I still need: " + ", ".join(clarification["remaining"]) + ".")
            answer = {"intent": "CLARIFICATION", "reply": reply, "model_mode": "deterministic", "citations": []}
        else:
            answer = guide_answer(context, body.message)
        record_guide_turn(case_id, "guide", answer["reply"], "text")
        with SessionLocal.begin() as session:
            add_event(session, case_id, "Travel Guide", "GUIDE_TEXT_ANSWERED", context["case_status"],
                      {"intent": answer["intent"], "selected_attraction": context["selected_attraction"]})
        return envelope(answer)
    except LookupError:
        fail("CASE_NOT_FOUND", "Case not found", 404)


@app.post("/api/cases/{case_id}/guide/revisions")
async def request_revision(case_id: str, body: RevisionRequest, request: Request):
    try:
        guide_context(case_id)
    except LookupError:
        fail("CASE_NOT_FOUND", "Case not found", 404)
    proposal_id = new_proposal_id()
    result = await request.app.state.revision_graph.ainvoke(
        {"case_id": case_id, "request": body.request, "proposal_id": proposal_id},
        config={"configurable": {"thread_id": f"guide:{case_id}:{proposal_id}"}},
    )
    if result.get("error"):
        fail("REVISION_UNAVAILABLE", result["error"], 409)
    return envelope(guide_context(case_id))


@app.post("/api/cases/{case_id}/guide/revisions/decision")
def decide_revision(case_id: str, body: RevisionDecision):
    try:
        return envelope(confirm_revision(case_id, body.proposal_id, body.accept))
    except LookupError:
        fail("CASE_NOT_FOUND", "Case not found", 404)
    except ValueError as exc:
        fail("INVALID_REVISION", str(exc), 409)


@app.websocket("/api/cases/{case_id}/guide/live")
async def guide_live(websocket: WebSocket, case_id: str):
    import base64
    import os

    origin = websocket.headers.get("origin", "")
    if not voice_origin_allowed(origin, websocket.headers.get("host", "")):
        await websocket.close(code=1008)
        return
    protocol = websocket.headers.get("sec-websocket-protocol", "")
    token = protocol.removeprefix("case-token.") if protocol.startswith("case-token.") else None
    if not await run_in_threadpool(valid_case_token, case_id, token):
        await websocket.close(code=1008)
        return
    if not os.getenv("GEMINI_API_KEY"):
        await websocket.close(code=1013)
        return
    try:
        context = guide_context(case_id)
    except LookupError:
        await websocket.close(code=1008)
        return
    limit_reached = False
    with SessionLocal.begin() as session:
        current = session.get(Case, case_id, with_for_update=True)
        state = current.guide_state or {}
        count = int(state.get("live_session_count", 0))
        if count >= settings.max_live_sessions_per_case:
            limit_reached = True
    if limit_reached:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    started = False
    stage = "provider_connect"
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        system = ("You are a calm travel companion for a New Zealand demo. Call get_current_trip before "
                  "answering about itinerary details. Use only the returned case facts. "
                  "Do not claim a visit, price, inventory or booking is confirmed. "
                  "Suggest rest when needed. Ask the user to review any revised itinerary proposal in the app. "
                  "A hotel, package, price or transport change requires a new Case and fresh verification.")
        config = {"response_modalities": ["AUDIO"], "input_audio_transcription": {},
                  "output_audio_transcription": {}, "system_instruction": system,
                  "tools": [{"function_declarations": [{"name": "get_current_trip",
                      "description": "Read the current case destination, selected attraction and illustrative days.",
                      "parameters": {"type": "OBJECT", "properties": {}}}]}]}
        async with client.aio.live.connect(model=settings.gemini_live_model, config=config) as session:
            with SessionLocal.begin() as db_session:
                current = db_session.get(Case, case_id, with_for_update=True)
                state = current.guide_state or {}
                count = int(state.get("live_session_count", 0))
                if count >= settings.max_live_sessions_per_case:
                    raise RuntimeError("Voice session limit reached")
                current.guide_state = {**state, "live_session_count": count + 1}
                add_event(db_session, case_id, "Travel Guide", "VOICE_SESSION_STARTED", current.status,
                          {"session_number": count + 1, "model": settings.gemini_live_model})
            started = True
            await websocket.send_json({"event": "connected"})
            stage = "streaming"
            revision_handled = False

            async def from_browser():
                while True:
                    event = await websocket.receive()
                    if event.get("type") == "websocket.disconnect":
                        break
                    if event.get("bytes"):
                        chunk = event["bytes"]
                        if len(chunk) > 65536:
                            await websocket.send_json({"event": "error", "message": "Audio chunk is too large"})
                            continue
                        await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
                    elif event.get("text"):
                        import json
                        control = json.loads(event["text"])
                        if control.get("event") == "stop":
                            await session.send_realtime_input(audio_stream_end=True)
                            break
                        if control.get("event") == "text" and isinstance(control.get("value"), str):
                            await session.send_realtime_input(text=control["value"][:1000])

            async def from_gemini():
                nonlocal revision_handled
                while True:
                    async for response in session.receive():
                        if response.tool_call:
                            results = []
                            for call in response.tool_call.function_calls:
                                if call.name == "get_current_trip":
                                    latest = guide_context(case_id)
                                    payload = {key: latest[key] for key in
                                               ("destination", "travel_pace", "traveler_count", "elevator_required",
                                                "selected_attraction", "days", "case_status", "location_mode")}
                                else:
                                    payload = {"error": "Unknown tool"}
                                results.append(types.FunctionResponse(name=call.name, id=call.id,
                                                                      response={"result": payload}))
                                with SessionLocal.begin() as db_session:
                                    current = db_session.get(Case, case_id)
                                    add_event(db_session, case_id, "Travel Guide", "GEMINI_TOOL_CALLED", current.status,
                                              {"tool": call.name, "read_only": True})
                            await session.send_tool_response(function_responses=results)
                        content = response.server_content
                        if not content:
                            continue
                        inbound = getattr(content, "input_transcription", None)
                        if inbound and inbound.text:
                            record_guide_turn(case_id, "traveler", inbound.text, "voice")
                            await websocket.send_json({"event": "heard", "text": inbound.text})
                            try:
                                clarification = await collect_spoken_clarification(case_id, inbound.text,
                                                                                  websocket.scope["app"])
                                if clarification:
                                    await websocket.send_json({"event": "clarification", **clarification})
                            except HTTPException as exc:
                                await websocket.send_json({"event": "revision_unavailable",
                                                           "message": exc.detail.get("message", "Clarification failed")})
                            if not revision_handled and classify_intent(inbound.text) == "REVISION":
                                revision_handled = True
                                proposal_id = new_proposal_id()
                                result = await websocket.scope["app"].state.revision_graph.ainvoke(
                                    {"case_id": case_id, "request": inbound.text[:500], "proposal_id": proposal_id},
                                    config={"configurable": {"thread_id": f"guide:{case_id}:{proposal_id}"}},
                                )
                                if not result.get("error"):
                                    await websocket.send_json({"event": "proposal", "guide": guide_context(case_id)})
                                else:
                                    await websocket.send_json({"event": "revision_unavailable", "message": result["error"]})
                        outbound = getattr(content, "output_transcription", None)
                        if outbound and outbound.text:
                            record_guide_turn(case_id, "guide", outbound.text, "voice")
                            await websocket.send_json({"event": "said", "text": outbound.text})
                        turn = getattr(content, "model_turn", None)
                        if turn:
                            for part in turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    await websocket.send_json({"event": "audio", "data": base64.b64encode(part.inline_data.data).decode("ascii")})
                        if getattr(content, "turn_complete", False):
                            await websocket.send_json({"event": "turn_complete"})

            incoming = asyncio.create_task(from_browser())
            outgoing = asyncio.create_task(from_gemini())
            done, pending = await asyncio.wait({incoming, outgoing}, timeout=300,
                                               return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            with SessionLocal.begin() as session:
                current = session.get(Case, case_id)
                if current:
                    add_event(session, case_id, "Travel Guide", "VOICE_SESSION_FAILED", current.status,
                              {"stage": stage, "error_type": type(exc).__name__})
        except Exception:
            pass
        try:
            message = ("Gemini Live could not start. Please retry or use the text guide." if stage == "provider_connect"
                       else "The voice stream ended unexpectedly. Please retry or use the text guide.")
            await websocket.send_json({"event": "error", "message": message})
        except Exception:
            pass
    finally:
        if started:
            try:
                with SessionLocal.begin() as session:
                    current = session.get(Case, case_id)
                    if current:
                        add_event(session, case_id, "Travel Guide", "VOICE_SESSION_ENDED", current.status, {})
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/api/cases/{case_id}/offers")
def offers(case_id: str):
    with SessionLocal() as session:
        case = get_case_or_404(session, case_id)
        rows = session.scalars(select(Offer).where(Offer.case_id == case_id).order_by(Offer.total_amount)).all()
        assessments = {a.offer_id: a for a in session.scalars(select(OfferAssessment).join(Offer, Offer.id == OfferAssessment.offer_id)
                                                               .where(Offer.case_id == case_id)).all()}
        approvals = session.scalars(select(Approval).where(Approval.case_id == case_id)).all()
        final_ids = {a.offer_id for a in approvals}
        data = []
        for row in rows:
            assessment = assessments.get(row.id)
            label = "VERIFIED" if row.id in final_ids and assessment and assessment.verdict == "PASS" else (
                "BLOCKED" if assessment and assessment.verdict == "BLOCK" else "REVIEW" if assessment and assessment.verdict == "REVIEW" else "PRELIMINARY")
            data.append({"id": row.id, "case_id": row.case_id, "product_id": row.catalog_product_id,
                         "version": row.version, "total_amount": money(row.total_amount), "currency": row.currency,
                         "includes": row.includes, "supplier_claims": row.supplier_claims,
                         "expires_at": iso(row.expires_at), "label": label,
                         "verdict": assessment.verdict if assessment else None,
                         "reason_code": assessment.reason_code if assessment else None})
        return envelope(data)


@app.get("/api/cases/{case_id}/evidence")
def evidence(case_id: str):
    with SessionLocal() as session:
        get_case_or_404(session, case_id)
        source_rows = session.execute(select(Evidence, Offer).join(Offer, Offer.id == Evidence.offer_id)
                                      .where(Offer.case_id == case_id)).all()
        assessment_rows = session.execute(select(OfferAssessment, Offer).join(Offer, Offer.id == OfferAssessment.offer_id)
                                          .where(Offer.case_id == case_id)).all()
        return envelope({"sources": [{"offer_id": o.id, "product_id": o.catalog_product_id,
                                      "claim_type": e.claim_type, "source": e.source, "polarity": e.polarity,
                                      "strength": e.source_strength, "reference": e.source_reference,
                                      "detail": e.detail, "source_time": iso(e.source_time)} for e, o in source_rows],
                         "assessments": [{"offer_id": o.id, "product_id": o.catalog_product_id,
                                          "claim_type": a.claim_type, "verdict": a.verdict,
                                          "reason_code": a.reason_code, "source_refs": a.source_refs} for a, o in assessment_rows]})


@app.get("/api/cases/{case_id}/approvals")
def approvals(case_id: str):
    with SessionLocal() as session:
        get_case_or_404(session, case_id)
        row = session.scalar(select(Approval).where(Approval.case_id == case_id).order_by(Approval.created_at.desc()))
        return envelope(None if not row else {"approval_id": row.id, "case_id": row.case_id, "offer_id": row.offer_id,
                                              "offer_version": row.offer_version, "approved_amount": money(row.approved_amount),
                                              "currency": row.currency, "case_state_version": row.case_state_version,
                                              "status": row.status, "nonce": demo_nonce(row.id) if row.status == "PENDING" else None})


@app.post("/api/cases/{case_id}/approvals/{approval_id}/decision")
async def decision(case_id: str, approval_id: str, body: Decision, request: Request):
    if body.decision not in {"APPROVE", "REJECT"}:
        fail("INVALID_DECISION", "Decision must be APPROVE or REJECT", 400)
    task = request.app.state.tasks.get(case_id)
    if task:
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5)
        except asyncio.TimeoutError:
            fail("GRAPH_NOT_PAUSED", "Workflow is still reaching the approval checkpoint")
    try:
        status, changed = decide_approval(case_id, approval_id, body.decision, body.nonce,
                                          body.expected_state_version)
    except ValueError as exc:
        fail("STALE_OFFER" if str(exc) == "STALE_OFFER" else "APPROVAL_CONFLICT", str(exc))
    if changed:
        launch(request.app, case_id, resume=True)
    return envelope({"approval_id": approval_id, "status": status, "accepted": True})


@app.get("/api/cases/{case_id}/orders")
def orders(case_id: str):
    with SessionLocal() as session:
        get_case_or_404(session, case_id)
        rows = session.scalars(select(Order).where(Order.case_id == case_id)).all()
        return envelope([{"id": o.id, "case_id": o.case_id, "offer_id": o.offer_id,
                          "approval_id": o.approval_id, "status": o.status,
                          "total_amount": money(o.total_amount), "currency": o.currency,
                          "created_at": iso(o.created_at)} for o in rows])


@app.get("/api/cases/{case_id}/events")
def events(case_id: str):
    with SessionLocal() as session:
        get_case_or_404(session, case_id)
        rows = session.scalars(select(AuditEvent).where(AuditEvent.case_id == case_id).order_by(AuditEvent.id)).all()
        return envelope([{"id": e.id, "agent_name": e.agent_name, "event_type": e.event_type,
                          "status": e.status, "payload": e.payload, "created_at": iso(e.created_at)} for e in rows])


@app.post("/api/cases/{case_id}/resume")
async def resume_case(case_id: str, request: Request):
    with SessionLocal() as session:
        case = get_case_or_404(session, case_id)
        if case.status != "RECOVERY_REQUIRED" or case_id in request.app.state.tasks:
            fail("INVALID_STATE", "Case is not available for recovery")
    launch(request.app, case_id, resume=True)
    return envelope({"case_id": case_id, "accepted": True})
