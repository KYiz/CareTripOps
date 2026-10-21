"""Structured logging, request correlation, and optional error reporting."""

import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone

from app.config import settings

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
# Attributes every LogRecord has; anything else was passed through `extra=` and is logged as a field.
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime", "taskName"}
_REDACT = {"email", "to", "body", "code", "token", "password", "authorization", "cookie"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
                 "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        if request_id := request_id_var.get():
            entry["request_id"] = request_id
        for key, value in vars(record).items():
            if key not in _STANDARD and not key.startswith("_"):
                entry[key] = "[redacted]" if key in _REDACT else value
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Readable lines for local development; development login codes are shown here on purpose."""
    def format(self, record: logging.LogRecord) -> str:
        extras = {k: v for k, v in vars(record).items() if k not in _STANDARD and not k.startswith("_")}
        rid = request_id_var.get()
        line = f"{record.levelname:<7} {record.name}: {record.getMessage()}"
        if rid:
            line += f" [request_id={rid}]"
        if extras:
            line += " " + " ".join(f"{k}={v}" for k, v in extras.items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else ConsoleFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level)
    # Uvicorn's own access log duplicates the structured access log written by the API middleware.
    logging.getLogger("uvicorn.access").disabled = True
    if settings.sentry_dsn:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.app_env, send_default_pii=False,
                        traces_sample_rate=0.0)


def incoming_request_id(header: str | None) -> str | None:
    return header if header and REQUEST_ID_PATTERN.match(header) else None
