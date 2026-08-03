"""
Logging configuration — structured JSON in deployed environments, readable
plain text locally, with a per-request correlation id threaded through both.

Call ``setup_logging()`` once at startup (before the app starts serving). Add
``RequestIdMiddleware`` to the app so every log line emitted while handling a
request carries its ``request_id`` — which is also returned to the client in the
``X-Request-ID`` header so a user-reported error can be traced to its logs.
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Correlation id for the in-flight request. Empty string when logging outside a
# request (startup, scheduler jobs, etc.).
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        return True


class _JsonFormatter(logging.Formatter):
    """One JSON object per line — friendly to Railway/Datadog log ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _PlainFormatter(logging.Formatter):
    """Compact, colourless human format for local dev."""

    def format(self, record: logging.LogRecord) -> str:
        rid = getattr(record, "request_id", "-")
        base = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} [{rid}] {record.name}: {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup_logging(app_env: str, level: str = "INFO") -> None:
    """Configure the root logger idempotently. JSON in deployed envs, plain locally."""
    root = logging.getLogger()
    root.setLevel(level)
    # Reset handlers so re-invocation (tests, reload) doesn't stack duplicates.
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(_PlainFormatter() if app_env == "local" else _JsonFormatter())
    root.addHandler(handler)

    # Uvicorn's own loggers should flow through our handler, not double-print.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign/propagate an X-Request-ID and bind it to the logging context."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = rid
        return response


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject over-large request bodies early (413) so a single request can't
    exhaust memory. Checks the Content-Length header — the common case; streaming
    bodies without a length are still bounded by the individual endpoints that
    read them (e.g. the resume upload cap)."""

    def __init__(self, app, max_bytes: int = 5 * 1024 * 1024):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > self.max_bytes:
                    from starlette.responses import JSONResponse

                    return JSONResponse(
                        {"detail": f"Request body too large (max {self.max_bytes // (1024 * 1024)} MB)."},
                        status_code=413,
                    )
            except ValueError:
                pass
        return await call_next(request)
