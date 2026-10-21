"""Supplier offer snapshots, their evidence, assessments, rankings and advisor reviews."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (UniqueConstraint("case_id", "catalog_product_id", "version"),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False)
    catalog_product_id: Mapped[str] = mapped_column(String(40), nullable=False)
    supplier: Mapped[str] = mapped_column(String(40), nullable=False, default="simulator")
    supplier_offer_ref: Mapped[str | None] = mapped_column(String(160))
    name: Mapped[str | None] = mapped_column(String(160))
    # Snapshot of what the traveler approves: features used for ranking and the refund rules.
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cancellation_policy: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
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
    source_url: Mapped[str | None] = mapped_column(String(500))
    # SHA-256 of the evidence as retrieved, so later edits at the source are detectable.
    content_hash: Mapped[str | None] = mapped_column(String(64))
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


class OfferRanking(Base):
    """Why an offer ranked where it did, per ranking round, in factors a person can read."""
    __tablename__ = "offer_rankings"
    __table_args__ = (UniqueConstraint("offer_id", "rank_round"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    offer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("offers.id"), nullable=False)
    rank_round: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    factors: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ReviewTask(Base):
    """An offer whose evidence was inconclusive, waiting for a travel advisor's decision."""
    __tablename__ = "review_tasks"
    __table_args__ = (Index("uq_open_review", "offer_id", "claim_type", unique=True,
                            postgresql_where=text("status = 'OPEN'")),)
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False, index=True)
    offer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("offers.id"), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(80), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

