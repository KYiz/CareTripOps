"""Email one-time-code login, cookie sessions, and per-Case role checks."""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.db import Case, CaseMember, LoginCode, SessionLocal, User, UserSession
from app.errors import fail

SESSION_COOKIE = "caretrip_session"
# ADVISOR is CareTrip staff reading a trip they are not a member of: viewer-level, and only for reads.
ROLE_RANK = {"VIEWER": 1, "ADVISOR": 1, "CO_PLANNER": 2, "OWNER": 3}
MAX_CODE_ATTEMPTS = 5
# Bump when the Terms of Use or Privacy Notice change materially; everyone accepts again at next sign-in.
TERMS_VERSION = "2026-10"
EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        raise ValueError("Enter a valid email address")
    return email


PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(value: str) -> str:
    """E.164. New Zealand numbers may be typed locally: 021 555 0100 becomes +64215550100."""
    phone = re.sub(r"[\s().-]", "", value.strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    elif phone.startswith("0"):
        phone = "+64" + phone[1:]
    elif phone.startswith("64"):
        phone = "+" + phone
    if not PHONE_PATTERN.match(phone):
        raise ValueError("Enter a mobile number such as 021 555 0100 or +64 21 555 0100")
    return phone


def phone_identifier(phone: str) -> str:
    return f"tel:{phone}"


def _digest(*parts: str) -> str:
    return hmac.new(settings.auth_secret.encode(), "\x1f".join(parts).encode(), hashlib.sha256).hexdigest()


def issue_login_code(identifier: str, purpose: str = "login") -> str:
    """Create a fresh code and retire any earlier unused code for this address (or phone) and purpose."""
    code = f"{secrets.randbelow(10 ** 6):06d}"
    with SessionLocal.begin() as session:
        for old in session.scalars(select(LoginCode).where(LoginCode.identifier == identifier, LoginCode.purpose == purpose,
                                                           LoginCode.consumed_at.is_(None))).all():
            old.consumed_at = now()
        session.add(LoginCode(identifier=identifier, purpose=purpose, code_hash=_digest(purpose, identifier, code),
                              expires_at=now() + timedelta(minutes=settings.login_code_minutes)))
    return code


def _matching_code(session, identifier: str, purpose: str, code: str) -> LoginCode | None:
    """The latest unused code if it matches. A wrong guess counts against it; the caller consumes a match."""
    row = session.scalar(select(LoginCode).where(LoginCode.identifier == identifier, LoginCode.purpose == purpose,
                                                 LoginCode.consumed_at.is_(None))
                         .order_by(LoginCode.created_at.desc()).limit(1).with_for_update())
    if not row or row.expires_at <= now() or row.attempts >= MAX_CODE_ATTEMPTS:
        return None
    if not hmac.compare_digest(row.code_hash, _digest(purpose, identifier, code.strip())):
        row.attempts += 1
        return None
    return row


def _invalid_code():
    fail("LOGIN_CODE_INVALID", "That code is not valid. Check the latest email or request a new code.", 400)


def account_for(session, identifier: str) -> User | None:
    if identifier.startswith("tel:"):
        return session.scalar(select(User).where(User.phone == identifier[4:], User.deleted_at.is_(None)))
    return session.scalar(select(User).where(User.email == identifier))


def verify_login_code(identifier: str, code: str, accept_terms: bool = False) -> tuple[User, str]:
    """Consume a valid code and open a session. Wrong guesses count against the code.

    An email address may open a new account; a phone number only signs in to the account that verified it.
    Someone who has not accepted the current terms keeps their code and is asked to accept them first.
    """
    outcome = "invalid"
    by_phone = identifier.startswith("tel:")
    with SessionLocal.begin() as session:
        row = _matching_code(session, identifier, "login", code)
        existing = account_for(session, identifier) if row else None
        if by_phone and not existing:
            row = None
        if row and not accept_terms and (not existing or existing.terms_version != TERMS_VERSION):
            outcome = "terms"
        elif row:
            outcome = "ok"
            row.consumed_at = now()
            if not by_phone:
                # Concurrent first logins for one address must not fail on the unique email.
                session.execute(insert(User).values(id=str(uuid4()), email=identifier, created_at=now())
                                .on_conflict_do_nothing(index_elements=["email"]))
            user = account_for(session, identifier)
            user.last_login_at = now()
            if accept_terms and user.terms_version != TERMS_VERSION:
                user.terms_version, user.terms_accepted_at = TERMS_VERSION, now()
            token = secrets.token_urlsafe(32)
            session.add(UserSession(user_id=user.id, token_hash=_digest("session", token), reauthenticated_at=now(),
                                    expires_at=now() + timedelta(days=settings.session_days)))
            session.flush()
            session.expunge(user)
    if outcome == "terms":
        fail("TERMS_REQUIRED", "Please read and accept the Terms of Use and Privacy Notice to continue.", 409)
    if outcome == "invalid":
        _invalid_code()
    return user, token


def _session_row(session, token: str | None) -> UserSession | None:
    if not token:
        return None
    return session.scalar(select(UserSession).where(UserSession.token_hash == _digest("session", token),
                                                    UserSession.revoked_at.is_(None), UserSession.expires_at > now()))


def confirm_phone(user: User, phone: str, code: str) -> None:
    """A code texted to the number proves the traveler holds it; then it can be used to sign in."""
    outcome = "invalid"
    with SessionLocal.begin() as session:
        row = _matching_code(session, phone_identifier(phone), "phone", code)
        if row:
            owner = session.scalar(select(User).where(User.phone == phone, User.id != user.id))
            outcome = "taken" if owner else "ok"
            row.consumed_at = now()
            if not owner:
                account = session.get(User, user.id)
                account.phone, account.phone_verified_at = phone, now()
    if outcome == "taken":
        fail("PHONE_TAKEN", "This mobile number is already used by another CareTrip account.", 409)
    if outcome == "invalid":
        _invalid_code()


def confirm_step_up(token: str | None, user: User, code: str) -> None:
    """A code sent to the signed-in address marks this session as freshly confirmed."""
    matched = False
    with SessionLocal.begin() as session:
        row = _matching_code(session, user.email, "step_up", code)
        current = _session_row(session, token)
        if row and current:
            matched = True
            row.consumed_at = current.reauthenticated_at = now()
    if not matched:
        _invalid_code()


def require_recent_auth(request: Request) -> None:
    """Sensitive actions need a sign-in or step-up code confirmed within STEP_UP_MINUTES."""
    with SessionLocal() as session:
        row = _session_row(session, request.cookies.get(SESSION_COOKIE))
        fresh = row and row.reauthenticated_at and now() - row.reauthenticated_at <= timedelta(minutes=settings.step_up_minutes)
    if not fresh:
        fail("STEP_UP_REQUIRED", "For your safety, please confirm with a code sent to your email.", 403)


def session_user(token: str | None) -> User | None:
    if not token:
        return None
    with SessionLocal.begin() as session:
        row = _session_row(session, token)
        if not row:
            return None
        if now() - row.last_seen_at > timedelta(hours=1):
            row.last_seen_at = now()
            row.expires_at = now() + timedelta(days=settings.session_days)
        user = session.get(User, row.user_id)
        if user.deleted_at:
            return None
        session.expunge(user)
        return user


def revoke_session(token: str | None) -> None:
    if not token:
        return
    with SessionLocal.begin() as session:
        row = session.scalar(select(UserSession).where(UserSession.token_hash == _digest("session", token)))
        if row and not row.revoked_at:
            row.revoked_at = now()


def member_role(case_id: str, user_id: str) -> str | None:
    if not UUID_PATTERN.match(case_id):
        return None
    with SessionLocal() as session:
        return session.scalar(select(CaseMember.role).where(CaseMember.case_id == case_id,
                                                            CaseMember.user_id == user_id))


def is_advisor(user: User) -> bool:
    return user.email in settings.advisor_emails


def access_role(case_id: str, user: User, method: str = "GET") -> str | None:
    """The member's role, or ADVISOR when CareTrip staff read a trip to support it. Staff never act for a traveler."""
    role = member_role(case_id, user.id)
    if role or method not in ("GET", "HEAD") or not is_advisor(user) or not UUID_PATTERN.match(case_id):
        return role
    with SessionLocal() as session:
        return "ADVISOR" if session.get(Case, case_id) else None


def require_user(request: Request) -> User:
    user = session_user(request.cookies.get(SESSION_COOKIE))
    if not user:
        fail("AUTH_REQUIRED", "Please sign in to continue.", 401)
    request.state.user_id = user.id
    return user


@dataclass(frozen=True)
class CaseAccess:
    case_id: str
    user: User
    role: str

    @property
    def is_owner(self) -> bool:
        return self.role == "OWNER"


def case_role(minimum: str):
    """Dependency: the signed-in user must be a member of the Case with at least this role."""
    def dependency(case_id: str, request: Request, user: User = Depends(require_user)) -> CaseAccess:
        role = access_role(case_id, user, request.method)
        if not role:
            # Same answer for missing and foreign Cases, so Case IDs cannot be probed.
            fail("CASE_NOT_FOUND", "Case not found", 404)
        if ROLE_RANK[role] < ROLE_RANK[minimum]:
            fail("ROLE_FORBIDDEN", "Your role on this trip does not allow this action.", 403)
        request.state.case_id = case_id
        return CaseAccess(case_id=case_id, user=user, role=role)
    return dependency
