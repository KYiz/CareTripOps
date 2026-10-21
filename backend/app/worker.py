"""Workflow worker: claims queued jobs and drives the LangGraph workflow for each Case.

Run as its own process with `python -m app.worker`. When EMBEDDED_WORKER=true (the default outside
Compose) the API runs one in-process instead, so a single `uvicorn` still works for development.
"""

import asyncio
import logging
import os
import signal
import socket
import time
from datetime import timedelta

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from sqlalchemy import update

from app import booking, companion, jobs, notify
from app.config import settings, validate_settings
from app.db import Case, Job, SessionLocal, set_status
from app.graph import build_graph
from app.suppliers import SupplierError

log = logging.getLogger("caretrip.worker")
HEARTBEAT_SECONDS = 5
REAP_SECONDS = 10
STALE_AFTER = timedelta(seconds=30)
SHUTDOWN_GRACE_SECONDS = 20
TERMINAL = {"BOOKED", "REJECTED", "HUMAN_REVIEW", "CANCELLED"}
HOUSEKEEPING_SECONDS = 2
REMINDER_SECONDS = 600  # Departure reminders are deduplicated, so the interval only bounds lateness.


def _fail_run(job: Job, error: str) -> None:
    """Close the job and flag the Case for an explicit, human-triggered recovery, in one transaction."""
    with SessionLocal.begin() as session:
        case = session.get(Case, job.case_id, with_for_update=True)
        if case and case.status not in TERMINAL:
            set_status(session, case, "RECOVERY_REQUIRED", "runner", "Manager", "RUN_FAILED", {"error_type": error})
        session.execute(update(Job).where(Job.id == job.id, Job.status == "RUNNING").values(
            status="FAILED", last_error=error[:200], finished_at=jobs.now()))


async def graph_input(graph, job: Job, config: dict):
    """Pick up where the Case's checkpoint left off: answer an interrupt, continue after a failed step,
    or start fresh when there is no checkpoint yet."""
    state = await graph.aget_state(config)
    if not state.next:
        return {"case_id": job.case_id} if job.kind == "start" else Command(resume=True)
    if any(task.interrupts for task in state.tasks):
        return Command(resume=True)
    return None


async def drive(graph, job: Job) -> None:
    config = {"configurable": {"thread_id": job.case_id}}
    started = time.monotonic()
    try:
        if job.kind == "cancel":
            await asyncio.to_thread(booking.process_cancellation, job.payload["order_id"])
        else:
            await graph.ainvoke(await graph_input(graph, job, config), config=config)
    except asyncio.CancelledError:
        await asyncio.to_thread(_fail_run, job, "WorkerShutdown")
        raise
    except Exception as exc:
        supplier_error = isinstance(exc, SupplierError)
        code = exc.code if supplier_error else type(exc).__name__
        # A supplier outage is temporary: try the same step again later rather than stopping the trip.
        if supplier_error and exc.retryable and await asyncio.to_thread(jobs.retry_later, job.id, code):
            log.warning("supplier unavailable; run re-queued", extra={"job_id": job.id, "case_id": job.case_id})
            return
        if not supplier_error:
            log.exception("workflow run failed", extra={"job_id": job.id, "case_id": job.case_id})
        if job.kind == "cancel":
            await asyncio.to_thread(booking.cancellation_failed, job.payload["order_id"], code)
        await asyncio.to_thread(_fail_run, job, code)
    else:
        await asyncio.to_thread(jobs.finish, job.id)
        log.info("workflow run finished", extra={"job_id": job.id, "case_id": job.case_id, "kind": job.kind,
                                                 "duration_ms": round((time.monotonic() - started) * 1000)})


class Worker:
    def __init__(self, graph, worker_id: str, concurrency: int, poll_seconds: float):
        self.graph, self.worker_id = graph, worker_id
        self.concurrency, self.poll_seconds = concurrency, poll_seconds
        self.running: dict[int, asyncio.Task] = {}

    async def run(self, stop: asyncio.Event) -> None:
        log.info("worker started", extra={"worker_id": self.worker_id, "concurrency": self.concurrency})
        last_beat = last_reap = last_housekeeping = last_reminders = 0.0
        while not stop.is_set():
            claimed = False
            while len(self.running) < self.concurrency and not stop.is_set():
                job = await asyncio.to_thread(jobs.claim, self.worker_id)
                if not job:
                    break
                claimed = True
                task = asyncio.create_task(drive(self.graph, job))
                self.running[job.id] = task
                task.add_done_callback(lambda _, job_id=job.id: self.running.pop(job_id, None))
            clock = time.monotonic()
            if clock - last_beat >= HEARTBEAT_SECONDS:
                await asyncio.to_thread(jobs.heartbeat, list(self.running))
                last_beat = clock
            if clock - last_housekeeping >= HOUSEKEEPING_SECONDS:
                await asyncio.to_thread(self.housekeeping)
                last_housekeeping = clock
            if clock - last_reminders >= REMINDER_SECONDS:
                await asyncio.to_thread(self.remind)
                last_reminders = clock
            if clock - last_reap >= REAP_SECONDS:
                flagged = await asyncio.to_thread(jobs.reap, STALE_AFTER)
                if flagged:
                    log.warning("interrupted runs flagged for recovery", extra={"case_ids": flagged})
                last_reap = clock
            if not claimed:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self.poll_seconds)
                except TimeoutError:
                    pass
        await self.shutdown()

    @staticmethod
    def housekeeping() -> None:
        """Send queued emails and release payments abandoned past the supplier hold."""
        try:
            notify.send_pending()
            booking.expire_stale_payments()
        except Exception:
            log.exception("housekeeping failed")

    @staticmethod
    def remind() -> None:
        try:
            companion.queue_trip_reminders()
        except Exception:
            log.exception("trip reminders failed")

    async def shutdown(self) -> None:
        if not self.running:
            return
        tasks = list(self.running.values())
        _, pending = await asyncio.wait(tasks, timeout=SHUTDOWN_GRACE_SECONDS)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def main() -> None:
    from app.observability import configure_logging
    configure_logging()
    validate_settings(settings)
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    async with AsyncPostgresSaver.from_conn_string(dsn) as checkpointer:
        await checkpointer.setup()
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await Worker(build_graph(checkpointer), worker_id(), settings.worker_concurrency,
                     settings.worker_poll_seconds).run(stop)


if __name__ == "__main__":
    asyncio.run(main())
