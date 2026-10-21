import os

import pytest

from app.ratelimit import RedisLimiter, SlidingWindowLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_limit_is_enforced_per_key_and_expires_after_the_window():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(window_seconds=60, clock=clock)
    assert limiter.acquire({"ip:a": 2}) is None
    assert limiter.acquire({"ip:a": 2}) is None
    assert limiter.acquire({"ip:a": 2}) == 60
    assert limiter.acquire({"ip:b": 2}) is None
    clock.now += 61
    assert limiter.acquire({"ip:a": 2}) is None


def test_a_full_global_key_blocks_without_consuming_the_client_key():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(window_seconds=60, clock=clock)
    assert limiter.acquire({"ip:a": 5, "global": 1}) is None
    assert limiter.acquire({"ip:b": 5, "global": 1}) is not None
    clock.now += 61
    assert limiter.acquire({"ip:b": 1, "global": 1}) is None


def test_retry_after_reports_time_until_the_oldest_hit_expires():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(window_seconds=60, clock=clock)
    limiter.acquire({"k": 1})
    clock.now += 45
    assert limiter.acquire({"k": 1}) == 15


REDIS_URL = os.environ.get("TEST_REDIS_URL", "")


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL is not set")
def test_redis_limiter_is_shared_between_processes_and_all_or_nothing():
    import redis
    from uuid import uuid4

    client = redis.Redis.from_url(REDIS_URL)
    name = f"test-{uuid4().hex[:8]}"
    first, second = RedisLimiter(client, name, 60), RedisLimiter(client, name, 60)  # Two API processes.
    assert first.acquire({"ip:a": 2}) is None
    assert second.acquire({"ip:a": 2}) is None
    assert 1 <= first.acquire({"ip:a": 2}) <= 60
    # A full key blocks the whole request, and the other key is not charged for it.
    assert second.acquire({"ip:a": 2, "email:x": 1}) is not None
    assert first.acquire({"email:x": 1}) is None
    assert client.pttl(f"caretrip:rl:{name}:ip:a") > 0


def test_a_redis_outage_does_not_lock_people_out():
    import redis

    limiter = RedisLimiter(redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.1), "down", 60)
    assert limiter.acquire({"ip:a": 1}) is None
