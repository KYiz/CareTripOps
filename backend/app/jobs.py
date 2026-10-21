"""PostgreSQL-backed job queue for workflow runs.

A partial unique index allows one QUEUED or RUNNING job per Case, so a Case is never driven by two
workers at once, across any number of API and worker processes.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.db import Case, Job, SessionLocal, set_status

ACTIVE = ("QUEUED", "RUNNING")
# Statuses a Case passes through only while a run is in progress. Interrupted waits
# (NEEDS_CLARIFICATION, AWAITING_APPROVAL) and terminal states are not listed.
IN_FLIGHT_STATUSES = ("RECEIVED", "REQUIREMENTS_READY", "OFFERS_DISCOVERED", "EVIDENCE_REVIEW",
                      "EVIDENCE_CONFLICT", "OFFERS_VERIFIED", "APPROVED", "BOOKING")
MAX_RETRIES = 5
RETRY_BASE_SECONDS = 5.0


class JobAlreadyActive(Exception):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(session, case_id: str, kind: str, payload: dict | None = None) -> None:
    """Queue a run inside the caller's transaction, so the state change and the job commit together."""
    try:
        with session.begin_nested():
            session.add(Job(case_id=case_id, kind=kind, status="QUEUED", attempts=0, payload=payload or {},
                            run_after=now()))
    except IntegrityError as exc:
        raise JobAlreadyActive(case_id) from exc


def active_job(case_id: str) -> Job | None:
    with SessionLocal() as session:
        job = session.scalar(select(Job).where(Job.case_id == case_id, Job.status.in_(ACTIVE)))
        if job:
            session.expunge(job)
        return job


def run_state(case_id: str) -> str:
    job = active_job(case_id)
    return job.status.lower() if job else "idle"


def claim(worker_id: str) -> Job | None:
    with SessionLocal.begin() as session:
        job = session.scalar(select(Job).where(Job.status == "QUEUED", Job.run_after <= now()).order_by(Job.id)
                             .limit(1).with_for_update(skip_locked=True))
        if not job:
            return None
        job.status, job.worker_id = "RUNNING", worker_id
        job.attempts += 1
        job.started_at = job.heartbeat_at = now()
        session.flush()
        session.expunge(job)
        return job


def finish(job_id: int, error: str | None = None) -> None:
    with SessionLocal.begin() as session:
        session.execute(update(Job).where(Job.id == job_id, Job.status == "RUNNING").values(
            status="FAILED" if error else "DONE", last_error=error[:200] if error else None, finished_at=now()))


def retry_later(job_id: int, error: str) -> bool:
    """Re-queue a run that hit a temporary outage, with exponential backoff. False once retries run out."""
    with SessionLocal.begin() as session:
        job = session.get(Job, job_id, with_for_update=True)
        if job.attempts >= MAX_RETRIES:
            return False
        job.status, job.worker_id, job.last_error = "QUEUED", None, error[:200]
        job.run_after = now() + timedelta(seconds=min(300, RETRY_BASE_SECONDS * 2 ** (job.attempts - 1)))
        return True


def heartbeat(job_ids: list[int]) -> None:
    if not job_ids:
        return
    with SessionLocal.begin() as session:
        session.execute(update(Job).where(Job.id.in_(job_ids), Job.status == "RUNNING").values(heartbeat_at=now()))


def reap(stale_after: timedelta) -> list[str]:
    """Fail runs whose worker stopped heartbeating, and flag Cases left mid-run without a job.

    Recovery stays an explicit decision (POST /resume), matching the earlier restart behaviour:
    a run may have produced side effects before its worker died.
    """
    flagged = []
    with SessionLocal.begin() as session:
        stale = session.scalars(select(Job).where(Job.status == "RUNNING", Job.heartbeat_at < now() - stale_after)
                                .with_for_update(skip_locked=True)).all()
        for job in stale:
            job.status, job.finished_at, job.last_error = "FAILED", now(), "worker heartbeat lost"
        session.flush()
        orphans = session.scalars(select(Case).where(
            Case.status.in_(IN_FLIGHT_STATUSES),
            ~select(Job.id).where(Job.case_id == Case.id, Job.status.in_(ACTIVE)).exists(),
            # Give a just-committed Case and its job time to become visible together.
            Case.updated_at < now() - timedelta(seconds=5),
        ).with_for_update(skip_locked=True)).all()
        for case in orphans:
            set_status(session, case, "RECOVERY_REQUIRED", "reaper", "Manager", "RUN_INTERRUPTED", {})
            flagged.append(case.id)
    return flagged
