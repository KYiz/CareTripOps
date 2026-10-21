"""Background work and support: the job queue, the email outbox, help requests and advisor notes."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class Job(Base):
    """One workflow run for a Case. At most one QUEUED or RUNNING job exists per Case."""
    __tablename__ = "jobs"
    __table_args__ = (Index("uq_active_job_per_case", "case_id", unique=True,
                            postgresql_where=text("status IN ('QUEUED', 'RUNNING')")),
                      Index("ix_jobs_queued", "id", postgresql_where=text("status = 'QUEUED'")))
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED")
    # Retryable failures (a supplier outage) are re-queued for later instead of failing the run.
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(80))
    last_error: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(Base):
    """Outbox: emails are written in the same transaction as the event, then sent by the worker."""
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_pending", "id", postgresql_where=text("status = 'PENDING'")),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"))
    to_email: Mapped[str] = mapped_column(String(254), nullable=False)
    template: Mapped[str] = mapped_column(String(40), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(200))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set for messages that must go out once only (trip reminders); a second insert is ignored.
    dedupe_key: Mapped[str | None] = mapped_column(String(160), unique=True)


class HelpRequest(Base):
    """A traveler or family member asking for help during the trip; advisors acknowledge it."""
    __tablename__ = "help_requests"
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    acknowledged_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    advisor_note: Mapped[str | None] = mapped_column(Text)



class CaseNote(Base):
    """An advisor's working note on a trip; only advisors see these."""
    __tablename__ = "case_notes"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("cases.id"), nullable=False, index=True)
    author_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
