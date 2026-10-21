"""Trips: create, read, clarify, approve, recover, and the read models behind both views.

Every Case route depends on `case_role`, which also guarantees the Case exists.
"""

import asyncio
import os
import time
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app import case_state, clarification, config, jobs
from app.api import common
from app.api.bookings import orders_view
from app.api.common import client_ip, envelope, iso, money, rate_limited
from app.auth import SESSION_COOKIE, CaseAccess, access_role, case_role, require_recent_auth, require_user, session_user
from app.db import (Approval, AuditEvent, Case, CaseMember, Evidence, Offer, OfferAssessment, OfferRanking, Requirement,
                    ReviewTask, SessionLocal, User, add_event, offer_verdicts)
from app.errors import fail
from app.events import case_event_stream
from app.guide_text import language_of
from app.skills.effects import decide_approval, demo_nonce
from app.two_brains import planning_enabled

router = APIRouter()
NEXT_ACTION = {"NEEDS_CLARIFICATION": "CLARIFY", "AWAITING_APPROVAL": "DECIDE", "AWAITING_PAYMENT": "PAY"}


class CreateCase(BaseModel):
    request: str = Field(min_length=8, max_length=2000)
    demo_date: date | None = None
    voice_draft: bool = False


class Clarification(BaseModel):
    answers: dict[str, str | int | float]


class Decision(BaseModel):
    decision: str
    nonce: str
    expected_state_version: int


@router.post("/api/cases", status_code=201)
def create_case(body: CreateCase, request: Request, user: User = Depends(require_user)):
    settings = config.settings
    required_key = "GEMINI_API_KEY" if settings.llm_provider == "gemini" else "OPENAI_API_KEY"
    if settings.model_mode == "api" and not os.getenv(required_key):
        fail("MODEL_UNAVAILABLE", f"Live model mode requires {required_key}", 503)
    rate_limited(common.case_limiter, {f"ip:{client_ip(request)}": settings.case_create_limit_per_ip,
                                f"user:{user.id}": settings.case_create_limit_per_ip,
                                "global": settings.case_create_limit_global},
                 "Too many new trips were started. Please try again later.")
    provider = settings.llm_provider if settings.model_mode == "api" else None
    with SessionLocal.begin() as session:
        case_id = str(uuid4())
        session.add(Case(id=case_id, thread_id=case_id, language=language_of(request.headers.get("accept-language")),
                         original_request=body.request, demo_date=body.demo_date, voice_draft=body.voice_draft,
                         requirements_model_mode=settings.model_mode, requirements_provider=provider))
        session.flush()
        session.add(CaseMember(case_id=case_id, user_id=user.id, role="OWNER"))
        add_event(session, case_id, "Manager", "CASE_CREATED", "RECEIVED",
                  {"model_mode": settings.model_mode, "llm_provider": provider})
        jobs.enqueue(session, case_id, "start")
    return envelope({"case_id": case_id, "thread_id": case_id, "status": "RECEIVED", "role": "OWNER"})


def _model_status(session, case: Case) -> str:
    if case.requirements_model_mode == "mock_llm":
        return "MOCK"
    seen = set(session.scalars(select(AuditEvent.event_type).where(
        AuditEvent.case_id == case.id, AuditEvent.event_type.in_(["MODEL_USAGE", "MODEL_ERROR", "MODEL_CALL_LIMIT"]))).all())
    return ("FAILED" if seen & {"MODEL_ERROR", "MODEL_CALL_LIMIT"} else "SUCCEEDED" if "MODEL_USAGE" in seen
            else "PENDING")


def case_view(session, access: CaseAccess) -> dict:
    case_id = access.case_id
    case = session.get(Case, case_id)
    req = session.scalar(select(Requirement).where(Requirement.case_id == case_id))
    itinerary = case_state.current_itinerary(session, case_id)
    days, source = (itinerary.days, itinerary.source) if itinerary else ([], "DETERMINISTIC_DRAFT")
    if req and not itinerary:
        if not req.missing_fields and planning_enabled() and case.status not in {"HUMAN_REVIEW", "RECOVERY_REQUIRED", "REJECTED"}:
            source = "PENDING"  # The Gemini planner is still writing the first outline.
        else:
            days = case_state.draft_days(req, case.language, case.original_request)
    requirements = None if not req else {
        "destination": req.destination, "departure_date": iso(req.departure_date),
        "destination_scope": req.destination_scope, "attractions": req.attractions, "travel_pace": req.travel_pace,
        "traveler_count": req.traveler_count, "duration_days": req.duration_days, "budget": money(req.budget),
        "currency": req.currency, "missing_fields": req.missing_fields,
        # Health-related needs are for the traveler and those helping plan, not every viewer.
        "hard_constraints": req.hard_constraints if access.role != "VIEWER" else
        {key: value for key, value in req.hard_constraints.items() if key != "needs"}}
    return {
        "case_id": case.id, "status": case.status, "active_node": case.active_node,
        "state_version": case.state_version, "requirements": requirements, "draft_itinerary": days,
        "itinerary_source": source, "itinerary_version": itinerary.version if itinerary else 0,
        "missing_fields": req.missing_fields if req else [], "next_action": NEXT_ACTION.get(case.status),
        "model_mode": case.requirements_model_mode, "model_status": _model_status(session, case),
        "llm_provider": case.requirements_provider, "my_role": access.role, "run_state": jobs.run_state(case_id),
        "created_at": iso(case.created_at)}


@router.get("/api/cases/{case_id}")
def read_case(case_id: str, access: CaseAccess = Depends(case_role("VIEWER"))):
    with SessionLocal() as session:
        return envelope(case_view(session, access))


@router.post("/api/cases/{case_id}/clarifications")
def clarify(case_id: str, body: Clarification, access: CaseAccess = Depends(case_role("CO_PLANNER"))):
    return envelope(clarification.apply(case_id, body.answers))


@router.post("/api/cases/{case_id}/resume")
def resume_case(case_id: str, access: CaseAccess = Depends(case_role("CO_PLANNER"))):
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        if case.status != "RECOVERY_REQUIRED":
            fail("INVALID_STATE", "Case is not available for recovery")
        try:
            jobs.enqueue(session, case_id, "resume")
        except jobs.JobAlreadyActive:
            fail("INVALID_STATE", "This trip is already resuming")
        add_event(session, case_id, "Manager", "RECOVERY_REQUESTED", case.status, {"by_role": access.role})
    return envelope({"case_id": case_id, "accepted": True, "run_state": "queued"})


def approval_view(session, access: CaseAccess) -> dict | None:
    row = session.scalar(select(Approval).where(Approval.case_id == access.case_id).order_by(Approval.created_at.desc()))
    return None if not row else {
        "approval_id": row.id, "case_id": row.case_id, "offer_id": row.offer_id, "offer_version": row.offer_version,
        "approved_amount": money(row.approved_amount), "currency": row.currency,
        "case_state_version": row.case_state_version, "status": row.status,
        # Only the traveler can approve, so only they receive the nonce.
        "nonce": demo_nonce(row.id) if row.status == "PENDING" and access.is_owner else None}


@router.get("/api/cases/{case_id}/approvals")
def approvals(case_id: str, access: CaseAccess = Depends(case_role("VIEWER"))):
    with SessionLocal() as session:
        return envelope(approval_view(session, access))


@router.post("/api/cases/{case_id}/approvals/{approval_id}/decision")
async def decision(case_id: str, approval_id: str, body: Decision, request: Request,
                   access: CaseAccess = Depends(case_role("OWNER"))):
    if body.decision not in {"APPROVE", "REJECT"}:
        fail("INVALID_DECISION", "Decision must be APPROVE or REJECT", 400)
    if body.decision == "APPROVE":  # Approving spends money; declining never needs re-confirmation.
        await run_in_threadpool(require_recent_auth, request)
    # The run that prepared the approval may still be finishing its checkpoint.
    deadline = time.monotonic() + 5
    while await run_in_threadpool(jobs.active_job, case_id):
        if time.monotonic() > deadline:
            fail("GRAPH_NOT_PAUSED", "Workflow is still reaching the approval checkpoint", retryable=True)
        await asyncio.sleep(0.1)
    try:
        # Records the decision and queues the resumed run in one transaction.
        status, _ = await run_in_threadpool(decide_approval, case_id, approval_id, body.decision, body.nonce,
                                            body.expected_state_version)
    except jobs.JobAlreadyActive:
        fail("GRAPH_NOT_PAUSED", "Workflow is still reaching the approval checkpoint", retryable=True)
    except ValueError as exc:
        fail("STALE_OFFER" if str(exc) == "STALE_OFFER" else "APPROVAL_CONFLICT", str(exc))
    return envelope({"approval_id": approval_id, "status": status, "accepted": True})


def offers_view(session, case_id: str) -> list[dict]:
    """Every offer with its verdict per claim and its latest ranking, in a fixed number of queries."""
    approved = set(session.scalars(select(Approval.offer_id).where(Approval.case_id == case_id)).all())
    reviewing = set(session.scalars(select(ReviewTask.offer_id).where(ReviewTask.case_id == case_id,
                                                                      ReviewTask.status == "OPEN")).all())
    rows = session.scalars(select(Offer).where(Offer.case_id == case_id).order_by(Offer.total_amount)).all()
    verdicts = offer_verdicts(session, [row.id for row in rows])
    rankings: dict = {}
    for ranking in session.scalars(select(OfferRanking).where(OfferRanking.offer_id.in_([row.id for row in rows]))
                                   .order_by(OfferRanking.rank_round.desc())):
        rankings.setdefault(ranking.offer_id, ranking)
    result = []
    for row in rows:
        assessment, ranking = verdicts[row.id], rankings.get(row.id)
        verdict = assessment.verdict if assessment else None
        label = ("VERIFIED" if row.id in approved and verdict == "PASS" else
                 {"BLOCK": "BLOCKED", "REVIEW": "REVIEW"}.get(verdict, "PRELIMINARY"))
        result.append({
            "id": row.id, "case_id": row.case_id, "product_id": row.catalog_product_id, "name": row.name,
            "version": row.version, "total_amount": money(row.total_amount), "currency": row.currency,
            "includes": row.includes, "supplier_claims": row.supplier_claims, "attributes": row.attributes,
            "cancellation_policy": row.cancellation_policy, "expires_at": iso(row.expires_at), "label": label,
            "verdict": verdict, "reason_code": assessment.reason_code if assessment else None,
            "claims": {claim: item.verdict for claim, item in assessment.claims.items()} if assessment else {},
            "under_review": row.id in reviewing,
            "ranking": ranking and {"round": ranking.rank_round, "eligible": ranking.eligible,
                                    "score": float(ranking.score), "factors": ranking.factors}})
    return result


@router.get("/api/cases/{case_id}/offers")
def offers(case_id: str, access: CaseAccess = Depends(case_role("VIEWER"))):
    with SessionLocal() as session:
        return envelope(offers_view(session, case_id))


def evidence_view(session, case_id: str) -> dict:
    sources = session.execute(select(Evidence, Offer).join(Offer, Offer.id == Evidence.offer_id)
                              .where(Offer.case_id == case_id)).all()
    latest = {(offer.id, assessment.claim_type): (assessment, offer) for assessment, offer in session.execute(
        select(OfferAssessment, Offer).join(Offer, Offer.id == OfferAssessment.offer_id)  # Later versions win.
        .where(Offer.case_id == case_id).order_by(OfferAssessment.assessment_version)).all()}
    return {
        "sources": [{"offer_id": o.id, "product_id": o.catalog_product_id, "claim_type": e.claim_type,
                     "source": e.source, "polarity": e.polarity, "strength": e.source_strength,
                     "reference": e.source_reference, "detail": e.detail, "url": e.source_url,
                     "content_hash": e.content_hash, "source_time": iso(e.source_time)} for e, o in sources],
        "assessments": [{"offer_id": o.id, "product_id": o.catalog_product_id, "claim_type": a.claim_type,
                         "verdict": a.verdict, "version": a.assessment_version, "reason_code": a.reason_code,
                         "source_refs": a.source_refs} for a, o in latest.values()]}


def events_view(session, case_id: str) -> list[dict]:
    rows = session.scalars(select(AuditEvent).where(AuditEvent.case_id == case_id).order_by(AuditEvent.id)).all()
    return [{"id": e.id, "agent_name": e.agent_name, "event_type": e.event_type, "status": e.status,
             "payload": e.payload, "created_at": iso(e.created_at)} for e in rows]


@router.get("/api/cases/{case_id}/evidence")
def evidence(case_id: str, access: CaseAccess = Depends(case_role("VIEWER"))):
    with SessionLocal() as session:
        return envelope(evidence_view(session, case_id))


@router.get("/api/cases/{case_id}/events")
def events(case_id: str, access: CaseAccess = Depends(case_role("VIEWER"))):
    with SessionLocal() as session:
        return envelope(events_view(session, case_id))


@router.get("/api/cases/{case_id}/snapshot")
def snapshot(case_id: str, access: CaseAccess = Depends(case_role("VIEWER"))):
    """Everything both views show about a trip, read in one request and one database session."""
    with SessionLocal() as session:
        return envelope({"case": case_view(session, access), "offers": offers_view(session, case_id),
                         "evidence": evidence_view(session, case_id), "approval": approval_view(session, access),
                         "orders": orders_view(session, case_id, access.is_owner),
                         "events": events_view(session, case_id)})


@router.get("/api/cases/{case_id}/stream")
async def case_stream(request: Request, access: CaseAccess = Depends(case_role("VIEWER"))):
    """Server-sent events: `changed` whenever the Case's audit trail or run state changes."""
    token = request.cookies.get(SESSION_COOKIE)

    async def still_allowed() -> bool:
        user = await run_in_threadpool(session_user, token)
        return bool(user and await run_in_threadpool(access_role, access.case_id, user))

    return StreamingResponse(
        case_event_stream(request.app.state.notifier, access.case_id, request.is_disconnected, still_allowed),
        media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
