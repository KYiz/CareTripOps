"""Helpers shared by the API routers: response envelope, formatting, client IP, origin check, rate limits."""

from decimal import Decimal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import Request

from app import config
from app.errors import fail
from app.observability import request_id_var
from app.ratelimit import Limiter, make_limiter

# Shared through Redis when REDIS_URL is set; otherwise per process (one API process only).
case_limiter = make_limiter("case", 3600, config.settings.redis_url)
login_limiter = make_limiter("login", 3600, config.settings.redis_url)


def envelope(data):
    return {"data": data, "request_id": request_id_var.get() or str(uuid4())}


def iso(value):
    return value.isoformat() if value else None


def money(value):
    return f"{Decimal(value):.2f}" if value is not None else None


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-real-ip") if config.settings.trust_proxy else None
    return (forwarded or (request.client.host if request.client else "unknown")).strip()


def origin_allowed(origin: str, host: str) -> bool:
    """The configured site origin, the local demo origins, or the exact host serving this request."""
    if origin in {config.settings.frontend_origin, "http://localhost:8080", "http://127.0.0.1:8080"}:
        return True
    parsed = urlsplit(origin)
    return bool(host and parsed.scheme in {"http", "https"} and parsed.netloc.lower() == host.lower()
                and origin == f"{parsed.scheme}://{parsed.netloc}")


def rate_limited(limiter: Limiter, limits: dict[str, int], message: str) -> None:
    wait = limiter.acquire(limits)
    if wait is not None:
        fail("RATE_LIMITED", message, 429, retryable=True, headers={"Retry-After": str(int(wait))})
