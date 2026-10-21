"""The CareTrip API: app assembly, lifespan, middleware and error handling. Routes live in app.api.*."""

import asyncio
import hmac
import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from prometheus_client import CONTENT_TYPE_LATEST
from sqlalchemy import text

from app import config, metrics
from app.api import accounts, advisor, bookings, cases, companion, guide, phone, privacy, voice
from app.api.common import origin_allowed
from app.config import validate_settings
from app.db import engine
from app.errors import fail
from app.events import CaseNotifier
from app.graph import build_graph
from app.guide import build_revision_graph
from app.observability import configure_logging, incoming_request_id, request_id_var
from app.worker import Worker, worker_id

log = logging.getLogger("caretrip.api")
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
QUIET_PATHS = {"/healthz", "/readyz", "/api/readyz"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = config.settings
    configure_logging()
    validate_settings(settings)
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    async with AsyncPostgresSaver.from_conn_string(dsn) as checkpointer:
        await checkpointer.setup()
        app.state.revision_graph = build_revision_graph(checkpointer)
        app.state.notifier = CaseNotifier(dsn)
        await app.state.notifier.start()
        stop = asyncio.Event()
        worker_task = None
        if settings.embedded_worker:
            worker = Worker(build_graph(checkpointer), f"api:{worker_id()}", settings.worker_concurrency,
                            settings.worker_poll_seconds)
            worker_task = asyncio.create_task(worker.run(stop))
        try:
            yield
        finally:
            stop.set()
            if worker_task:
                await worker_task
            await app.state.notifier.stop()


production = config.settings.is_production
app = FastAPI(title="CareTrip Ops", lifespan=lifespan, redoc_url=None,
              docs_url=None if production else "/api/docs", openapi_url=None if production else "/api/openapi.json")
for module in (accounts, phone, privacy, cases, bookings, companion, advisor, guide, voice):
    app.include_router(module.router)


def _error(status: int, code: str, message: str, retryable: bool = False, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, headers=headers, content={
        "error": {"code": code, "message": message, "retryable": retryable}, "request_id": request_id_var.get()})


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):
    """CSRF guard for cookie sessions: browsers always send Origin on cross-site writes."""
    if request.method in UNSAFE_METHODS and request.url.path.startswith("/api/"):
        origin, fetch_site = request.headers.get("origin"), request.headers.get("sec-fetch-site")
        if (origin and not origin_allowed(origin, request.headers.get("host", ""))) or \
                (fetch_site and fetch_site not in {"same-origin", "none"}):
            return _error(403, "CROSS_SITE_REQUEST", "Cross-site requests are not allowed.")
    return await call_next(request)


# Registered after same_origin_writes, so it wraps it and sees every request.
@app.middleware("http")
async def observe_requests(request: Request, call_next):
    """Correlate logs with one request ID, echo it to the client, and log one line per request."""
    request_id = incoming_request_id(request.headers.get("x-request-id")) or uuid4().hex
    token = request_id_var.set(request_id)
    started, status = time.monotonic(), 500
    try:
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"path": request.url.path})
            response = _error(500, "INTERNAL_ERROR", "Something went wrong. Please try again.", retryable=True)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        route = getattr(request.scope.get("route"), "path", None)
        if request.url.path != "/metrics":
            # Unmatched paths share one label so scanners cannot blow up the series count.
            metrics.observe(request.method, route or "unmatched", status, time.monotonic() - started)
        if request.url.path not in QUIET_PATHS:
            log.info("request", extra={
                "method": request.method, "route": route or request.url.path,
                "status": status, "duration_ms": round((time.monotonic() - started) * 1000, 1),
                "user_id": getattr(request.state, "user_id", None), "case_id": getattr(request.state, "case_id", None)})
        request_id_var.reset(token)


@app.exception_handler(RequestValidationError)
async def validation_error(_, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(part) for part in first.get("loc", [])[1:]) or "request"
    return _error(422, "INVALID_REQUEST", f"Please check {field}: {first.get('msg', 'invalid value')}.")


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
    return _error(exc.status_code, detail["code"], detail["message"], detail.get("retryable", False), exc.headers)


@app.exception_handler(LookupError)
async def not_found(_, exc: LookupError):
    # Raised by domain code when a Case vanished between the access check and the read.
    return _error(404, "CASE_NOT_FOUND", "Case not found")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics(request: Request):
    """Scraped on the internal network (Nginx does not proxy it); METRICS_TOKEN adds a bearer check."""
    token = config.settings.metrics_token
    if token and not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
        fail("UNAUTHORIZED", "Metrics need a valid token", 401)
    return Response(metrics.render(), media_type=CONTENT_TYPE_LATEST)


@app.get("/readyz")
@app.get("/api/readyz")
def readyz():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        fail("DB_UNAVAILABLE", "Database is unavailable", 503)
    settings = config.settings
    return {"status": "ready", "model_mode": settings.model_mode,
            "llm_provider": settings.llm_provider if settings.model_mode == "api" else None}
