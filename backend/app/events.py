"""Live Case updates: one shared PostgreSQL LISTEN connection fanned out to server-sent event streams."""

import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable

import psycopg

log = logging.getLogger("caretrip.events")
CHANNEL = "case_events"
HEARTBEAT_SECONDS = 15
COALESCE_SECONDS = 0.2


class CaseNotifier:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self.connected = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def _signal(self, queue: asyncio.Queue) -> None:
        # One pending signal is enough: the browser re-reads the whole Case on each "changed".
        if queue.empty():
            queue.put_nowait(None)

    def _broadcast(self) -> None:
        for queues in self.subscribers.values():
            for queue in queues:
                self._signal(queue)

    async def _listen(self) -> None:
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(self.dsn, autocommit=True) as conn:
                    await conn.execute(f"LISTEN {CHANNEL}")
                    self.connected.set()
                    # Anything may have changed while disconnected; let every stream catch up.
                    self._broadcast()
                    async for note in conn.notifies():
                        for queue in list(self.subscribers.get(note.payload, ())):
                            self._signal(queue)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.connected.clear()
                log.warning("case event listener disconnected; retrying", exc_info=True)
                await asyncio.sleep(2)

    @contextlib.contextmanager
    def subscribe(self, case_id: str):
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        self.subscribers[case_id].add(queue)
        try:
            yield queue
        finally:
            self.subscribers[case_id].discard(queue)
            if not self.subscribers[case_id]:
                del self.subscribers[case_id]


async def case_event_stream(notifier: CaseNotifier, case_id: str,
                            is_disconnected: Callable[[], Awaitable[bool]],
                            still_allowed: Callable[[], Awaitable[bool]],
                            heartbeat_seconds: float = HEARTBEAT_SECONDS) -> AsyncIterator[str]:
    """Yield SSE frames: `ready` once, `changed` after Case writes, comments as keep-alives.

    Access is re-checked on every heartbeat, so a removed family member or a signed-out session
    stops receiving updates within one interval.
    """
    with notifier.subscribe(case_id) as queue:
        yield "retry: 3000\nevent: ready\ndata: {}\n\n"
        while True:
            if await is_disconnected():
                return
            try:
                await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except TimeoutError:
                if not await still_allowed():
                    yield "event: revoked\ndata: {}\n\n"
                    return
                yield ": keep-alive\n\n"
                continue
            await asyncio.sleep(COALESCE_SECONDS)
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            yield "event: changed\ndata: {}\n\n"
