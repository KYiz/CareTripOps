from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, create_engine, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    thread_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    access_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    original_request: Mapped[str] = mapped_column(Text, nullable=False)
    demo_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="RECEIVED")
    active_node: Mapped[str] = mapped_column(String(80), nullable=False, default="start")
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clarification_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    guide_state: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
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


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (UniqueConstraint("case_id", "catalog_product_id", "version"),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False)
    catalog_product_id: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    includes: Mapped[list] = mapped_column(JSONB, nullable=False)
    supplier_claims: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    offer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("offers.id"), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    polarity: Mapped[str] = mapped_column(String(20), nullable=False)
    source_strength: Mapped[str] = mapped_column(String(20), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    source_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class OfferAssessment(Base):
    __tablename__ = "offer_assessments"
    __table_args__ = (UniqueConstraint("offer_id", "claim_type", "assessment_version"),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    offer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("offers.id"), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(80), nullable=False)
    verdict: Mapped[str] = mapped_column(String(12), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    assessment_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source_refs: Mapped[list] = mapped_column(JSONB, nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False)
    offer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("offers.id"), nullable=False)
    offer_version: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    case_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False)
    offer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("offers.id"), nullable=False)
    approval_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("approvals.id"), unique=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(60), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def add_event(session, case_id: str, agent: str, event_type: str, status: str, payload: dict | None = None):
    session.add(AuditEvent(case_id=case_id, agent_name=agent, event_type=event_type, status=status, payload=payload or {}))


def set_status(session, case: Case, status: str, node: str, agent: str, event_type: str, payload: dict | None = None):
    case.status = status
    case.active_node = node
    case.state_version += 1
    add_event(session, case.id, agent, event_type, status, payload)
