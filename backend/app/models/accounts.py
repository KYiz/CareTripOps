"""Users, sign-in codes, sessions and family membership."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A verified mobile number (E.164) that can also be used to sign in.
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terms_version: Mapped[str | None] = mapped_column(String(20))
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Explicit consent to store health and accessibility details in the traveler profile.
    sensitive_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginCode(Base):
    __tablename__ = "login_codes"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    # An email address, or "tel:+64..." for a code sent by text message.
    identifier: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # "login" opens a session; "step_up" re-confirms a signed-in person before a sensitive action.
    purpose: Mapped[str] = mapped_column(String(10), nullable=False, default="login", server_default="login")
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reauthenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TravelerProfile(Base):
    """Health and accessibility needs; stored only with the traveler's explicit consent."""
    __tablename__ = "traveler_profiles"
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), primary_key=True)
    needs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    emergency_contact: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CaseMember(Base):
    __tablename__ = "case_members"
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CaseInvitation(Base):
    __tablename__ = "case_invitations"
    __table_args__ = (Index("uq_open_invitation", "case_id", "email", unique=True,
                            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL")),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    invited_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

