"""The case-bound text guide and illustrative itinerary revisions."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import case_state, clarification
from app.api.common import envelope
from app.auth import CaseAccess, case_role
from app.db import Case, SessionLocal, add_event
from app.errors import fail
from app.guide import confirm_revision, guide_answer, guide_context, new_proposal_id, record_guide_turn, select_attraction
from app.guide_text import field_names, language_of, reply_text

router = APIRouter()


class GuideSelection(BaseModel):
    attraction: str = Field(min_length=1, max_length=120)


class GuideMessage(BaseModel):
    message: str = Field(min_length=2, max_length=1000)


class RevisionRequest(BaseModel):
    request: str = Field(min_length=5, max_length=500)


class DayEdit(BaseModel):
    day_number: int = Field(ge=1, le=30)
    title: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=1000)
    activities: list[str] = Field(default_factory=list, max_length=8)
    rest_note: str = Field(default="", max_length=300)


class ItineraryEdit(BaseModel):
    base_version: int
    days: list[DayEdit] = Field(min_length=1, max_length=30)


class RevisionDecision(BaseModel):
    proposal_id: str
    accept: bool


@router.get("/api/guide/capabilities")
def guide_capabilities():
    import os
    available = bool(os.getenv("GEMINI_API_KEY"))
    return envelope({"voice_available": available, "voice_provider": "Gemini Live" if available else None})


@router.get("/api/cases/{case_id}/guide")
def read_guide(case_id: str, access: CaseAccess = Depends(case_role("VIEWER"))):
    return envelope(guide_context(case_id))


@router.post("/api/cases/{case_id}/guide/attraction")
def update_guide_attraction(case_id: str, body: GuideSelection, access: CaseAccess = Depends(case_role("CO_PLANNER"))):
    try:
        return envelope(select_attraction(case_id, body.attraction))
    except ValueError as exc:
        fail("INVALID_ATTRACTION", str(exc), 422)


def answer_message(case_id: str, message: str, lang: str) -> dict:
    """A trip waiting for details takes the message as answers; otherwise the guide replies."""
    context = guide_context(case_id)
    record_guide_turn(case_id, "traveler", message, "text")
    heard = clarification.from_speech(case_id, message, lang)
    if heard:
        reply = (reply_text(lang, "clarified") if heard.get("saved") else heard.get("error")
                 or reply_text(lang, "still_need", fields=field_names(lang, heard["remaining"])))
        answer = {"intent": "CLARIFICATION", "reply": reply, "model_mode": "deterministic", "citations": []}
    else:
        answer = guide_answer(context, message, lang)
    record_guide_turn(case_id, "guide", answer["reply"], "text")
    with SessionLocal.begin() as session:
        add_event(session, case_id, "Travel Guide", "GUIDE_TEXT_ANSWERED", context["case_status"],
                  {"intent": answer["intent"], "selected_attraction": context["selected_attraction"]})
    return answer


@router.post("/api/cases/{case_id}/guide/messages")
def guide_message(case_id: str, body: GuideMessage, request: Request,
                  access: CaseAccess = Depends(case_role("CO_PLANNER"))):
    return envelope(answer_message(case_id, body.message, language_of(request.headers.get("accept-language"))))


async def propose_revision(app, case_id: str, request_text: str) -> str | None:
    """Run the revision graph; returns an error message, or None when a proposal was saved."""
    proposal_id = new_proposal_id()
    result = await app.state.revision_graph.ainvoke(
        {"case_id": case_id, "request": request_text, "proposal_id": proposal_id},
        config={"configurable": {"thread_id": f"guide:{case_id}:{proposal_id}"}})
    return result.get("error")


@router.post("/api/cases/{case_id}/guide/revisions")
async def request_revision(case_id: str, body: RevisionRequest, request: Request,
                           access: CaseAccess = Depends(case_role("CO_PLANNER"))):
    error = await propose_revision(request.app, case_id, body.request)
    if error:
        fail("REVISION_UNAVAILABLE", error, 409)
    return envelope(await run_in_threadpool(guide_context, case_id))


@router.post("/api/cases/{case_id}/guide/revisions/decision")
def decide_revision(case_id: str, body: RevisionDecision, access: CaseAccess = Depends(case_role("CO_PLANNER"))):
    try:
        return envelope(confirm_revision(case_id, body.proposal_id, body.accept))
    except ValueError as exc:
        fail("INVALID_REVISION", str(exc), 409)


@router.put("/api/cases/{case_id}/itinerary")
def edit_itinerary(body: ItineraryEdit, access: CaseAccess = Depends(case_role("CO_PLANNER"))):
    """The traveler's own wording becomes the next outline version; it stays illustrative and unverified."""
    edits = [{**day.model_dump(), "activities": [item.strip()[:200] for item in day.activities if item.strip()]}
             for day in body.days]
    with SessionLocal.begin() as session:
        case = session.get(Case, access.case_id, with_for_update=True)
        try:
            version = case_state.edit_itinerary(session, access.case_id, body.base_version, edits, access.user.id)
        except LookupError:
            fail("NO_ITINERARY", "There is no outline to edit yet.", 409)
        except ValueError as exc:
            if str(exc) == "ITINERARY_CHANGED":
                fail("ITINERARY_CHANGED", "Someone else changed the outline. Please look at the latest one first.")
            fail("INVALID_REQUEST", "Every day of the outline must be included once.", 400)
        if version != body.base_version:
            add_event(session, case.id, "Traveler", "ITINERARY_EDITED", case.status, {"version": version})
    return envelope({"version": version})
