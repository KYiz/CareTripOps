"""The travel advisor's console: trips, traveler needs, notes, evidence reviews and help requests."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import advisors, companion, reviews
from app.api.common import envelope
from app.auth import UUID_PATTERN, is_advisor, require_user
from app.db import User
from app.errors import fail

router = APIRouter()


class ReviewDecision(BaseModel):
    decision: str
    note: str = Field(default="", max_length=2000)


class Note(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class Acknowledgement(BaseModel):
    note: str = Field(default="", max_length=2000)


def require_advisor(user: User = Depends(require_user)) -> User:
    if not is_advisor(user):
        fail("ADVISOR_ONLY", "Only travel advisors can do this.", 403)
    return user


@router.get("/api/advisor/reviews")
def advisor_reviews(user: User = Depends(require_advisor)):
    return envelope(reviews.open_reviews())


@router.post("/api/advisor/reviews/{task_id}")
def advisor_decide(task_id: str, body: ReviewDecision, user: User = Depends(require_advisor)):
    return envelope(reviews.resolve(task_id, user, body.decision, body.note))


@router.get("/api/advisor/help")
def help_requests(user: User = Depends(require_advisor)):
    return envelope(companion.open_help_requests())


@router.post("/api/advisor/help/{help_id}")
def acknowledge_help(help_id: str, body: Acknowledgement, user: User = Depends(require_advisor)):
    try:
        acknowledged = companion.acknowledge_help(help_id, user, body.note)
    except LookupError:
        fail("HELP_NOT_FOUND", "Help request not found", 404)
    if not acknowledged:
        fail("HELP_ALREADY_ACKNOWLEDGED", "Another advisor already picked this up.")
    return envelope({"id": help_id, "acknowledged": True})


@router.get("/api/advisor/cases")
def advisor_cases(status: str | None = None, user: User = Depends(require_advisor)):
    return envelope(advisors.list_cases(status))


def _case_id(case_id: str) -> str:
    if not UUID_PATTERN.match(case_id):
        fail("CASE_NOT_FOUND", "Case not found", 404)
    return case_id


@router.get("/api/advisor/cases/{case_id}/traveler")
def traveler(case_id: str, user: User = Depends(require_advisor)):
    try:
        return envelope(advisors.traveler_profile(_case_id(case_id), user))
    except LookupError:
        fail("CASE_NOT_FOUND", "Case not found", 404)


@router.get("/api/advisor/cases/{case_id}/notes")
def case_notes(case_id: str, user: User = Depends(require_advisor)):
    return envelope(advisors.notes(_case_id(case_id)))


@router.post("/api/advisor/cases/{case_id}/notes", status_code=201)
def add_case_note(case_id: str, body: Note, user: User = Depends(require_advisor)):
    try:
        return envelope(advisors.add_note(_case_id(case_id), user, body.text))
    except LookupError:
        fail("CASE_NOT_FOUND", "Case not found", 404)
