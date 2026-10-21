"""Trips: the Case, its requirements, audit trail and guide data."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    thread_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    original_request: Mapped[str] = mapped_column(Text, nullable=False)
    demo_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="RECEIVED")
    active_node: Mapped[str] = mapped_column(String(80), nullable=False, default="start")
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clarification_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Language the traveler planned in; generated itinerary text follows it.
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    requirements_model_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="mock_llm")
    requirements_provider: Mapped[str | None] = mapped_column(String(20))
    voice_draft: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Details heard by voice while the Case waits for clarification, before they are applied.
    spoken_answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    selected_attraction: Mapped[str | None] = mapped_column(String(120))
    live_session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Requirement(Base):
    __tablename__ = "requirements"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), unique=True, nullable=False)
    destination: Mapped[str | None] = mapped_column(String(120))
    destination_scope: Mapped[str] = mapped_column(String(20), default="UNKNOWN", nullable=False)
    attractions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    travel_pace: Mapped[str] = mapped_column(String(20), default="STANDARD", nullable=False)
    departure_date: Mapped[datetime | None] = mapped_column(Date)
    traveler_count: Mapped[int | None] = mapped_column(Integer)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    budget: Mapped[float | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    hard_constraints: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    missing_fields: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(60), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ItineraryVersion(Base):
    """Every illustrative outline a Case has had; the highest version is current."""
    __tablename__ = "itinerary_versions"
    __table_args__ = (UniqueConstraint("case_id", "version"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    days: Mapped[list] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    model_trace: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(80))
    proposal_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ItineraryProposal(Base):
    __tablename__ = "itinerary_proposals"
    __table_args__ = (Index("uq_pending_proposal_case", "case_id", unique=True,
                            postgresql_where=text("status = 'PENDING'")),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False, index=True)
    request: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    days: Mapped[list] = mapped_column(JSONB, nullable=False)
    model_trace: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

