"""Gemini Live voice guide: a server-side bridge between the browser microphone and the model."""

import asyncio
import base64
import json
import os

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app import clarification, config
from app.api.common import origin_allowed
from app.api.guide import propose_revision
from app.auth import ROLE_RANK, SESSION_COOKIE, member_role, session_user
from app.db import Case, SessionLocal, add_event
from app.guide import guide_context, record_guide_turn
from app.guide_text import classify_intent

router = APIRouter()
SESSION_SECONDS = 300
MAX_AUDIO_CHUNK = 65536
SYSTEM_PROMPT = (
    "You are a calm travel companion for a New Zealand demo. Reply in the language the traveler speaks. "
    "Call get_current_trip before answering about itinerary details. Use only the returned case facts. "
    "Do not claim a visit, price, inventory or booking is confirmed. Suggest rest when needed. Ask the user to "
    "review any revised itinerary proposal in the app. A hotel, package, price or transport change requires a new "
    "Case and fresh verification. For questions about lifts, steps, bathrooms or wheelchairs at the stay, answer only "
    "from stay.verified_claims; anything not listed there has not been checked, so say so. Respect access_needs when "
    "suggesting what to do. In an emergency tell the traveler to call 111.")
TRIP_FIELDS = ("destination", "travel_pace", "traveler_count", "elevator_required", "access_needs", "stay",
               "selected_attraction", "days", "case_status", "location_mode")


def reserve_live_session(case_id: str) -> int | None:
    """Atomically claim one voice session slot before any provider connection is opened."""
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        if not case or case.live_session_count >= config.settings.max_live_sessions_per_case:
            return None
        case.live_session_count += 1
        return case.live_session_count


def release_live_session(case_id: str) -> None:
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id, with_for_update=True)
        if case:
            case.live_session_count = max(0, case.live_session_count - 1)


def _event(case_id: str, event_type: str, payload: dict | None = None) -> None:
    with SessionLocal.begin() as session:
        case = session.get(Case, case_id)
        if case:
            add_event(session, case_id, "Travel Guide", event_type, case.status, payload or {})


async def _authorized(websocket: WebSocket, case_id: str) -> int | None:
    """Same-origin, signed-in CO_PLANNER or better, provider configured, and a free session slot."""
    if not origin_allowed(websocket.headers.get("origin", ""), websocket.headers.get("host", "")):
        return await websocket.close(code=1008)
    # The session cookie rides on the same-origin handshake; voice can change plans, so it needs CO_PLANNER.
    user = await run_in_threadpool(session_user, websocket.cookies.get(SESSION_COOKIE))
    role = user and await run_in_threadpool(member_role, case_id, user.id)
    if not role or ROLE_RANK[role] < ROLE_RANK["CO_PLANNER"]:
        return await websocket.close(code=1008)
    if not os.getenv("GEMINI_API_KEY"):
        return await websocket.close(code=1013)
    slot = await run_in_threadpool(reserve_live_session, case_id)
    if slot is None:
        return await websocket.close(code=1008)
    return slot


@router.websocket("/api/cases/{case_id}/guide/live")
async def guide_live(websocket: WebSocket, case_id: str):
    slot = await _authorized(websocket, case_id)
    if slot is None:
        return
    await websocket.accept()
    started, stage = False, "provider_connect"
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        tool = {"name": "get_current_trip", "description": "Read the current case destination, selected attraction "
                "and illustrative days.", "parameters": {"type": "OBJECT", "properties": {}}}
        live_config = {"response_modalities": ["AUDIO"], "input_audio_transcription": {},
                       "output_audio_transcription": {}, "system_instruction": SYSTEM_PROMPT,
                       "tools": [{"function_declarations": [tool]}]}
        async with client.aio.live.connect(model=config.settings.gemini_live_model, config=live_config) as live:
            await run_in_threadpool(_event, case_id, "VOICE_SESSION_STARTED",
                                    {"session_number": slot, "model": config.settings.gemini_live_model})
            started, stage = True, "streaming"
            await websocket.send_json({"event": "connected"})
            language = (await run_in_threadpool(guide_context, case_id))["language"]
            bridge = _Bridge(websocket, live, types, case_id, language)
            tasks = {asyncio.create_task(bridge.from_browser()), asyncio.create_task(bridge.from_gemini())}
            done, pending = await asyncio.wait(tasks, timeout=SESSION_SECONDS, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await run_in_threadpool(_event, case_id, "VOICE_SESSION_FAILED", {"stage": stage, "error_type": type(exc).__name__})
        message = ("Gemini Live could not start. Please retry or use the text guide." if stage == "provider_connect"
                   else "The voice stream ended unexpectedly. Please retry or use the text guide.")
        try:
            await websocket.send_json({"event": "error", "message": message})
        except Exception:
            pass
    finally:
        if started:
            await run_in_threadpool(_event, case_id, "VOICE_SESSION_ENDED")
        else:
            await run_in_threadpool(release_live_session, case_id)  # The provider never connected.
        try:
            await websocket.close()
        except Exception:
            pass


class _Bridge:
    """Relays audio both ways and turns transcripts into saved turns, clarifications and revisions."""

    def __init__(self, websocket: WebSocket, live, types, case_id: str, language: str):
        self.websocket, self.live, self.types = websocket, live, types
        self.case_id, self.language = case_id, language
        self.revision_requested = False

    async def from_browser(self) -> None:
        while True:
            event = await self.websocket.receive()
            if event.get("type") == "websocket.disconnect":
                return
            if event.get("bytes"):
                if len(event["bytes"]) > MAX_AUDIO_CHUNK:
                    await self.websocket.send_json({"event": "error", "message": "Audio chunk is too large"})
                    continue
                await self.live.send_realtime_input(audio=self.types.Blob(data=event["bytes"], mime_type="audio/pcm;rate=16000"))
            elif event.get("text"):
                try:
                    control = json.loads(event["text"])
                except ValueError:
                    continue  # Not a control message we understand.
                if not isinstance(control, dict):
                    continue
                if control.get("event") == "stop":
                    await self.live.send_realtime_input(audio_stream_end=True)
                    return
                if control.get("event") == "text" and isinstance(control.get("value"), str):
                    await self.live.send_realtime_input(text=control["value"][:1000])

    async def from_gemini(self) -> None:
        while True:
            async for response in self.live.receive():
                if response.tool_call:
                    await self._answer_tools(response.tool_call.function_calls)
                content = response.server_content
                if not content:
                    continue
                heard = getattr(content, "input_transcription", None)
                if heard and heard.text:
                    await self._on_heard(heard.text)
                said = getattr(content, "output_transcription", None)
                if said and said.text:
                    await run_in_threadpool(record_guide_turn, self.case_id, "guide", said.text, "voice")
                    await self.websocket.send_json({"event": "said", "text": said.text})
                for part in getattr(getattr(content, "model_turn", None), "parts", None) or []:
                    if part.inline_data and part.inline_data.data:
                        await self.websocket.send_json({"event": "audio",
                                                        "data": base64.b64encode(part.inline_data.data).decode("ascii")})
                if getattr(content, "turn_complete", False):
                    await self.websocket.send_json({"event": "turn_complete"})

    async def _answer_tools(self, calls) -> None:
        results = []
        for call in calls:
            if call.name == "get_current_trip":
                trip = await run_in_threadpool(guide_context, self.case_id)
                payload = {key: trip[key] for key in TRIP_FIELDS}
            else:
                payload = {"error": "Unknown tool"}
            results.append(self.types.FunctionResponse(name=call.name, id=call.id, response={"result": payload}))
            await run_in_threadpool(_event, self.case_id, "GEMINI_TOOL_CALLED", {"tool": call.name, "read_only": True})
        await self.live.send_tool_response(function_responses=results)

    async def _on_heard(self, text: str) -> None:
        await run_in_threadpool(record_guide_turn, self.case_id, "traveler", text, "voice")
        await self.websocket.send_json({"event": "heard", "text": text})
        try:
            result = await run_in_threadpool(clarification.from_speech, self.case_id, text, self.language)
            if result:
                await self.websocket.send_json({"event": "clarification", **result})
        except HTTPException as exc:
            await self.websocket.send_json({"event": "revision_unavailable",
                                            "message": exc.detail.get("message", "Clarification failed")})
        if not self.revision_requested and classify_intent(text) == "REVISION":
            self.revision_requested = True
            error = await propose_revision(self.websocket.scope["app"], self.case_id, text[:500])
            if error:
                await self.websocket.send_json({"event": "revision_unavailable", "message": error})
            else:
                await self.websocket.send_json({"event": "proposal",
                                                "guide": await run_in_threadpool(guide_context, self.case_id)})
