"""A verified mobile number: text-message codes for signing in, managed from the Account page."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import config
from app.api import common
from app.api.common import envelope, rate_limited
from app.auth import confirm_phone, issue_login_code, normalize_phone, phone_identifier, require_user
from app.db import SessionLocal, User
from app.errors import fail
from app.sms import send_sms, sms_enabled

log = logging.getLogger("caretrip.api")
router = APIRouter()


class Phone(BaseModel):
    phone: str = Field(min_length=6, max_length=30)


class PhoneCode(Phone):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


def valid_phone(value: str) -> str:
    try:
        return normalize_phone(value)
    except ValueError as exc:
        fail("INVALID_PHONE", str(exc), 400)


def send_code_sms(phone: str, purpose: str) -> str:
    """Issue and text a code. Returns it so development can show it on screen."""
    if not sms_enabled():
        fail("SMS_UNAVAILABLE", "Codes by text message are not available. Please use your email address.", 400)
    code = issue_login_code(phone_identifier(phone), purpose)
    try:
        send_sms(phone, f"Your CareTrip code is {code}. It expires in {config.settings.login_code_minutes} minutes.")
    except Exception:
        log.exception("text message failed")
        fail("SMS_UNAVAILABLE", "We could not send the text message right now. Please use your email address.", 503,
             retryable=True)
    return code


def code_response(code: str | None) -> dict:
    settings = config.settings
    data = {"sent": True, "expires_in_minutes": settings.login_code_minutes}
    if code and settings.auth_dev_return_code and not settings.is_production:
        data["dev_code"] = code
    return data


@router.put("/api/auth/me/phone", status_code=202)
def add_phone(body: Phone, user: User = Depends(require_user)):
    phone = valid_phone(body.phone)
    rate_limited(common.login_limiter, {f"tel:{phone}": config.settings.login_code_limit_per_email,
                                        f"user:{user.id}": config.settings.login_code_limit_per_email},
                 "Too many codes were requested. Please wait and try again.")
    return envelope(code_response(send_code_sms(phone, "phone")))


@router.post("/api/auth/me/phone/verify")
def verify_phone(body: PhoneCode, user: User = Depends(require_user)):
    phone = valid_phone(body.phone)
    confirm_phone(user, phone, body.code)
    return envelope({"phone": phone, "verified": True})


@router.delete("/api/auth/me/phone")
def remove_phone(user: User = Depends(require_user)):
    with SessionLocal.begin() as session:
        row = session.get(User, user.id)
        row.phone = row.phone_verified_at = None
    return envelope({"removed": True})
