"""Approvals, orders and payments."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("uq_pending_approval_case", "case_id", unique=True,
                            postgresql_where=text("status = 'PENDING'")),)
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
    # PENDING_PAYMENT -> CONFIRMED -> CANCELLATION_REQUESTED -> CANCELLED, or FAILED at any step before CONFIRMED.
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    departure_date: Mapped[datetime | None] = mapped_column(Date)
    supplier_hold_ref: Mapped[str | None] = mapped_column(String(80))
    supplier_hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supplier_booking_ref: Mapped[str | None] = mapped_column(String(80))
    failure_reason: Mapped[str | None] = mapped_column(String(80))
    refund_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    order_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("orders.id"), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_ref: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    payment_intent_ref: Mapped[str | None] = mapped_column(String(120))
    # REQUIRES_ACTION -> AUTHORIZED -> CAPTURED (-> REFUNDED / PARTIALLY_REFUNDED); or RELEASED / EXPIRED / FAILED.
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    refunded_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    checkout_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class PaymentEvent(Base):
    """Provider webhook events already handled; the primary key makes redelivery harmless."""
    __tablename__ = "payment_events"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

