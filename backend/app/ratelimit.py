"""Sliding-window rate limits.

SlidingWindowLimiter keeps hits in this process, which is only correct for a single API process. With REDIS_URL set,
RedisLimiter keeps them in Redis so every API process shares one count.
"""

import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Protocol


class Limiter(Protocol):
    def acquire(self, limits: dict[str, int]) -> float | None: ...


class SlidingWindowLimiter:
    def __init__(self, window_seconds: float = 3600, clock=time.monotonic):
        self.window = window_seconds
        self.clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        return hits

    def acquire(self, limits: dict[str, int]) -> float | None:
        """Record one hit against every key, or none. Returns seconds to wait when any key is full."""
        with self._lock:
            now = self.clock()
            windows = {key: self._prune(key, now) for key in limits}
            full = [hits[0] + self.window - now for key, hits in windows.items() if len(hits) >= limits[key]]
            if full:
                return max(1.0, max(full))
            for hits in windows.values():
                hits.append(now)
            for key in [key for key, hits in self._hits.items() if not hits]:
                del self._hits[key]
            return None


log = logging.getLogger("caretrip.ratelimit")

# Atomic across all keys: either every key records the hit, or none does and the longest wait is returned (ms).
ACQUIRE_SCRIPT = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local window = tonumber(ARGV[1])
local wait = 0
for i, key in ipairs(KEYS) do
  redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
  if redis.call('ZCARD', key) >= tonumber(ARGV[i + 2]) then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    wait = math.max(wait, tonumber(oldest[2]) + window - now)
  end
end
if wait > 0 then return wait end
for i, key in ipairs(KEYS) do
  redis.call('ZADD', key, now, ARGV[2] .. ':' .. i)
  redis.call('PEXPIRE', key, window)
end
return 0
"""


class RedisLimiter:
    """The same contract as SlidingWindowLimiter, shared by every API process through Redis."""

    def __init__(self, client, name: str, window_seconds: float = 3600):
        self.client, self.prefix, self.window_ms = client, f"caretrip:rl:{name}:", int(window_seconds * 1000)
        self._script = client.register_script(ACQUIRE_SCRIPT)

    def acquire(self, limits: dict[str, int]) -> float | None:
        keys = [self.prefix + key for key in limits]
        try:
            wait_ms = int(self._script(keys=keys, args=[self.window_ms, uuid.uuid4().hex, *limits.values()]))
        except Exception:
            # An outage of the limiter must not lock everyone out of signing in; it is logged loudly instead.
            log.exception("rate limiter unavailable; allowing the request")
            return None
        return max(1.0, wait_ms / 1000) if wait_ms > 0 else None


def make_limiter(name: str, window_seconds: float = 3600, redis_url: str = ""):
    if not redis_url:
        return SlidingWindowLimiter(window_seconds=window_seconds)
    import redis

    return RedisLimiter(redis.Redis.from_url(redis_url, socket_timeout=0.5, socket_connect_timeout=0.5), name, window_seconds)
