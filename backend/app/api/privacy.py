"""Step-up confirmation, the traveler's needs profile, data export and account deletion."""

import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app import config, privacy
from app.api import common
from app.api.common import envelope, iso, rate_limited
from app.auth import SESSION_COOKIE, confirm_step_up, issue_login_code, require_recent_auth, require_user
from app.db import SessionLocal, TravelerProfile, User
from app.errors import fail
from app.mailer import send_email

log = logging.getLogger("caretrip.api")
router = APIRouter()

DIETARY = Literal["VEGETARIAN", "VEGAN", "GLUTEN_FREE", "HALAL", "KOSHER", "DIABETIC", "LOW_SODIUM", "NUT_ALLERGY",
                  "SOFT_FOOD"]


class StepUpCode(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class Needs(BaseModel):
    """What the traveler needs from rooms and days out; every field narrows supplier search and ranking."""
    wheelchair: Literal["NONE", "SOMETIMES", "MANUAL", "POWER"] = "NONE"
    max_walk_meters: int | None = Field(default=None, ge=0, le=20000)
    step_free: bool = False
    accessible_bathroom: bool = False
    dietary: list[DIETARY] = Field(default_factory=list, max_length=9)
    medical_notes: str = Field(default="", max_length=1000)


class EmergencyContact(BaseModel):
    name: str = Field(default="", max_length=80)
    relationship: str = Field(default="", max_length=40)
    phone: str = Field(default="", max_length=30, pattern=r"^[0-9+()\- ]*$")


class Profile(BaseModel):
    needs: Needs
    emergency_contact: EmergencyContact = Field(default_factory=EmergencyContact)


class Consent(BaseModel):
    granted: bool


def send_code_email(email: str, subject: str, intro: str, code: str) -> None:
    minutes = config.settings.login_code_minutes
    try:
        send_email(email, subject, f"{intro} {code}. It expires in {minutes} minutes. "
                                   "If you did not ask for it, you can ignore this email.")
    except Exception:
        log.exception("code email failed")
        fail("EMAIL_UNAVAILABLE", "We could not send the email right now. Please try again in a minute.", 503,
             retryable=True)


@router.post("/api/auth/step-up/request", status_code=202)
def request_step_up(user: User = Depends(require_user)):
    settings = config.settings
    rate_limited(common.login_limiter, {f"step:{user.id}": settings.login_code_limit_per_email},
                 "Too many codes were requested. Please wait and try again.")
    code = issue_login_code(user.email, "step_up")
    send_code_email(user.email, "Confirm your CareTrip action", "Your CareTrip confirmation code is", code)
    data = {"sent": True, "expires_in_minutes": settings.login_code_minutes}
    if settings.auth_dev_return_code and not settings.is_production:
        data["dev_code"] = code
    return envelope(data)


@router.post("/api/auth/step-up/verify")
def verify_step_up(body: StepUpCode, request: Request, user: User = Depends(require_user)):
    confirm_step_up(request.cookies.get(SESSION_COOKIE), user, body.code)
    return envelope({"confirmed": True, "valid_minutes": config.settings.step_up_minutes})


@router.put("/api/auth/me/consent")
def sensitive_consent(body: Consent, user: User = Depends(require_user)):
    privacy.set_sensitive_consent(user.id, body.granted)
    return envelope({"granted": body.granted})


def _profile_payload(row: TravelerProfile | None) -> dict:
    if not row:
        return {"needs": Needs().model_dump(), "emergency_contact": EmergencyContact().model_dump(), "updated_at": None}
    return {"needs": row.needs, "emergency_contact": row.emergency_contact, "updated_at": iso(row.updated_at)}


@router.get("/api/profile")
def read_profile(user: User = Depends(require_user)):
    with SessionLocal() as session:
        return envelope({**_profile_payload(session.get(TravelerProfile, user.id)),
                         "consent": session.get(User, user.id).sensitive_consent_at is not None})


@router.put("/api/profile")
def save_profile(body: Profile, user: User = Depends(require_user)):
    with SessionLocal.begin() as session:
        if not session.get(User, user.id).sensitive_consent_at:
            fail("CONSENT_REQUIRED", "Please agree to CareTrip storing your health and access needs first.", 409)
        row = session.get(TravelerProfile, user.id) or TravelerProfile(user_id=user.id)
        row.needs = body.needs.model_dump()
        row.emergency_contact = body.emergency_contact.model_dump()
        session.add(row)
        session.flush()
        return envelope({**_profile_payload(row), "consent": True})


@router.get("/api/auth/me/export")
def export_data(user: User = Depends(require_user)):
    body = json.dumps(envelope(privacy.export(user)), ensure_ascii=False, indent=2)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="caretrip-my-data.json"',
                             "Cache-Control": "no-store"})


@router.delete("/api/auth/me")
def delete_account(response: Response, user: User = Depends(require_user), _: None = Depends(require_recent_auth)):
    try:
        privacy.delete_account(user)
    except ValueError:
        fail("ACTIVE_BOOKINGS", "Please cancel or finish your current bookings before deleting the account.", 409)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return envelope({"deleted": True})
