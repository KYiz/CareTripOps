"""The trip companion: the printable trip card and the help button."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import companion
from app.api import common
from app.api.common import envelope, rate_limited
from app.auth import CaseAccess, case_role

router = APIRouter()


class HelpMessage(BaseModel):
    message: str = Field(default="", max_length=500)


@router.get("/api/cases/{case_id}/trip-card")
def trip_card(access: CaseAccess = Depends(case_role("VIEWER"))):
    return envelope(companion.trip_card(access.case_id, access.role))


@router.post("/api/cases/{case_id}/help", status_code=201)
def ask_for_help(body: HelpMessage, access: CaseAccess = Depends(case_role("VIEWER"))):
    # Anyone on the trip may ask; a few per hour stops an accidental flood of emails.
    rate_limited(common.case_limiter, {f"help:{access.case_id}": 5},
                 "Help was already requested several times. A CareTrip advisor will be in touch; in an emergency call 111.")
    return envelope(companion.request_help(access.case_id, access.user, body.message))
