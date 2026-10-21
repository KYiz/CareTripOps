"""Sign-in, profile, the traveler's trip list, and family sharing."""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app import config, members
from app.api import common
from app.api.common import client_ip, envelope, rate_limited
from app.api.phone import code_response, send_code_sms, valid_phone
from app.api.privacy import send_code_email
from app.auth import (SESSION_COOKIE, CaseAccess, account_for, case_role, is_advisor, issue_login_code, normalize_email,
                      phone_identifier, require_user, revoke_session, verify_login_code)
from app.db import SessionLocal, User
from app.errors import fail

router = APIRouter()


class Email(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class CodeRequest(BaseModel):
    """Sign in with an email address, or with a mobile number already verified on an account."""
    email: str | None = Field(default=None, min_length=3, max_length=254)
    phone: str | None = Field(default=None, min_length=6, max_length=30)


class LoginVerify(CodeRequest):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    accept_terms: bool = False


class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


class InvitationRequest(Email):
    role: str


class InvitationAnswer(BaseModel):
    accept: bool


def valid_email(value: str) -> str:
    try:
        return normalize_email(value)
    except ValueError as exc:
        fail("INVALID_EMAIL", str(exc), 400)


def login_identifier(body: CodeRequest) -> str:
    if bool(body.email) == bool(body.phone):
        fail("INVALID_REQUEST", "Please give an email address or a mobile number.", 400)
    return valid_email(body.email) if body.email else phone_identifier(valid_phone(body.phone))


def user_payload(user: User) -> dict:
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "is_advisor": is_advisor(user),
            "terms_version": user.terms_version, "sensitive_consent": user.sensitive_consent_at is not None,
            "phone": user.phone}


@router.post("/api/auth/request-code", status_code=202)
def request_login_code(body: CodeRequest, request: Request):
    settings = config.settings
    identifier = login_identifier(body)
    key = identifier if identifier.startswith("tel:") else f"email:{identifier}"
    rate_limited(common.login_limiter, {key: settings.login_code_limit_per_email,
                                        f"ip:{client_ip(request)}": settings.login_code_limit_per_ip},
                 "Too many sign-in codes were requested. Please wait and try again.")
    code = None
    if not identifier.startswith("tel:"):
        code = issue_login_code(identifier)
        send_code_email(identifier, "Your CareTrip sign-in code", "Your CareTrip sign-in code is", code)
    else:
        with SessionLocal() as session:
            known = account_for(session, identifier) is not None
        if known:
            code = send_code_sms(identifier[4:], "login")
    # The same answer whether or not an account exists, so addresses and numbers cannot be probed.
    return envelope(code_response(code))


@router.post("/api/auth/verify")
def verify_login(body: LoginVerify, response: Response):
    user, token = verify_login_code(login_identifier(body), body.code, body.accept_terms)
    response.set_cookie(SESSION_COOKIE, token, max_age=config.settings.session_days * 86400, httponly=True,
                        secure=config.settings.is_production, samesite="lax", path="/")
    return envelope(user_payload(user))


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    revoke_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return envelope({"signed_out": True})


@router.get("/api/auth/me")
def me(user: User = Depends(require_user)):
    return envelope(user_payload(user))


@router.patch("/api/auth/me")
def update_profile(body: ProfileUpdate, user: User = Depends(require_user)):
    with SessionLocal.begin() as session:
        row = session.get(User, user.id)
        row.display_name = body.display_name.strip()
        session.flush()
        session.expunge(row)
    return envelope(user_payload(row))


@router.get("/api/cases")
def list_cases(user: User = Depends(require_user)):
    return envelope(members.my_cases(user))


@router.get("/api/invitations")
def list_invitations(user: User = Depends(require_user)):
    return envelope(members.my_invitations(user))


@router.post("/api/invitations/{invitation_id}")
def answer_invitation(invitation_id: str, body: InvitationAnswer, user: User = Depends(require_user)):
    return envelope(members.answer_invitation(user, invitation_id, body.accept))


@router.get("/api/cases/{case_id}/members")
def case_members(access: CaseAccess = Depends(case_role("VIEWER"))):
    data = members.list_members(access.case_id, include_invitations=access.is_owner)
    return envelope({**data, "my_role": access.role})


@router.post("/api/cases/{case_id}/invitations", status_code=201)
def invite_member(body: InvitationRequest, access: CaseAccess = Depends(case_role("OWNER"))):
    return envelope(members.invite(access.case_id, access.user, valid_email(body.email), body.role))


@router.delete("/api/cases/{case_id}/invitations/{invitation_id}")
def revoke_invitation(invitation_id: str, access: CaseAccess = Depends(case_role("OWNER"))):
    members.revoke_invitation(access.case_id, invitation_id)
    return envelope({"revoked": True})


@router.delete("/api/cases/{case_id}/members/{user_id}")
def remove_member(user_id: str, access: CaseAccess = Depends(case_role("OWNER"))):
    members.remove_member(access.case_id, user_id)
    return envelope({"removed": True})
