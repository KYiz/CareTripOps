"""Live update plumbing: SSE frame generation, LISTEN/NOTIFY fan-out, and job queue guarantees."""
import asyncio

import pytest
from sqlalchemy import text

from app.config import settings
from app.events import CaseNotifier, case_event_stream


async def _collect(stream, count, timeout=5):
    frames = []
    async def run():
        async for frame in stream:
            frames.append(frame)
            if len(frames) == count:
                return
    await asyncio.wait_for(run(), timeout)
    return frames


def test_stream_sends_ready_then_changed_once_per_burst():
    async def scenario():
        notifier = CaseNotifier("unused")
        stream = case_event_stream(notifier, "case-1", is_disconnected=_never, still_allowed=_always,
                                   heartbeat_seconds=5)
        first = await stream.__anext__()
        assert "event: ready" in first
        queue = next(iter(notifier.subscribers["case-1"]))
        for _ in range(3):  # A burst of writes collapses into one "changed".
            notifier._signal(queue)
        assert "event: changed" in await asyncio.wait_for(stream.__anext__(), 2)
        await stream.aclose()
        assert "case-1" not in notifier.subscribers
    asyncio.run(scenario())


def test_stream_stops_when_access_is_revoked():
    async def scenario():
        notifier = CaseNotifier("unused")
        stream = case_event_stream(notifier, "case-1", is_disconnected=_never, still_allowed=_denied,
                                   heartbeat_seconds=0.05)
        frames = await _collect(stream, 2)
        assert "event: revoked" in frames[1]
    asyncio.run(scenario())


def test_stream_sends_keep_alives_while_idle():
    async def scenario():
        notifier = CaseNotifier("unused")
        stream = case_event_stream(notifier, "case-1", is_disconnected=_never, still_allowed=_always,
                                   heartbeat_seconds=0.05)
        frames = await _collect(stream, 3)
        assert frames[1].startswith(":") and frames[2].startswith(":")
        await stream.aclose()
    asyncio.run(scenario())


async def _never():
    return False


async def _always():
    return True


async def _denied():
    return False


def _database_available():
    try:
        from app.db import engine
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM jobs LIMIT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _database_available(), reason="Migrated PostgreSQL is unavailable")
def test_notify_reaches_only_subscribers_of_that_case():
    from app.db import engine

    async def scenario():
        notifier = CaseNotifier(settings.database_url.replace("postgresql+psycopg://", "postgresql://"))
        await notifier.start()
        try:
            await asyncio.wait_for(notifier.connected.wait(), 5)
            with notifier.subscribe("case-a") as mine, notifier.subscribe("case-b") as other:
                for queue in (mine, other):  # Drop the catch-up signal sent on connect.
                    while not queue.empty():
                        queue.get_nowait()
                with engine.begin() as connection:
                    connection.execute(text("SELECT pg_notify('case_events', 'case-a')"))
                await asyncio.wait_for(mine.get(), 5)
                await asyncio.sleep(0.2)
                assert other.empty()
        finally:
            await notifier.stop()
    asyncio.run(scenario())


@pytest.mark.skipif(not _database_available(), reason="Migrated PostgreSQL is unavailable")
def test_queue_allows_one_active_run_per_case_and_claims_each_job_once():
    from concurrent.futures import ThreadPoolExecutor
    from uuid import uuid4

    from app import jobs
    from app.db import Case, Job, SessionLocal

    case_id = str(uuid4())
    with SessionLocal.begin() as session:
        session.add(Case(id=case_id, thread_id=case_id, original_request="queue test", status="HUMAN_REVIEW",
                         active_node="test", state_version=0, clarification_count=0, llm_calls=0))
        session.flush()
        jobs.enqueue(session, case_id, "start")
        with pytest.raises(jobs.JobAlreadyActive):
            jobs.enqueue(session, case_id, "resume")
    # Hide this job from other workers' claim order by claiming concurrently from many threads.
    with ThreadPoolExecutor(max_workers=8) as pool:
        claimed = [job for job in pool.map(lambda n: jobs.claim(f"test-{n}"), range(8)) if job]
    mine = [job for job in claimed if job.case_id == case_id]
    assert len(mine) == 1
    assert jobs.run_state(case_id) == "running"
    jobs.finish(mine[0].id)
    assert jobs.run_state(case_id) == "idle"
    with SessionLocal.begin() as session:
        jobs.enqueue(session, case_id, "resume")  # A new run is allowed once the previous one is done.
        session.flush()
        for job in session.query(Job).filter(Job.case_id == case_id, Job.status == "QUEUED"):
            job.status = "DONE"  # Leave nothing for a later test's worker to pick up.
        for job in claimed:
            if job.case_id != case_id:  # Return anything else this test happened to claim.
                session.get(Job, job.id).status = "QUEUED"
