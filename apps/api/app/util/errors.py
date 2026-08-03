"""
Consistent error envelope (RFC 7807 problem+json).

Every error response gets the same shape — status, a machine-readable title, a
human detail, and the request's correlation id — so first-party clients and the
B2B partner API integrate against one contract instead of ad-hoc strings. Register
with ``install_error_handlers(app)``.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.util.logging_config import request_id_ctx

logger = logging.getLogger(__name__)

_CONTENT_TYPE = "application/problem+json"

# Map common statuses to a stable machine-readable title.
_TITLES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "upstream_error",
    503: "service_unavailable",
}


def _problem(status: int, detail: str, *, extra: dict | None = None) -> JSONResponse:
    body = {
        "type": f"about:blank#{_TITLES.get(status, 'error')}",
        "title": _TITLES.get(status, "error"),
        "status": status,
        "detail": detail,
        "request_id": request_id_ctx.get() or None,
    }
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=_CONTENT_TYPE)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        resp = _problem(exc.status_code, detail)
        # Preserve auth/rate-limit headers (WWW-Authenticate, Retry-After).
        for k, v in (getattr(exc, "headers", None) or {}).items():
            resp.headers[k] = v
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError):
        # Report which fields failed and why, but strip `input` (echoes the
        # user's submitted value) and `ctx` (may carry internal object reprs) so
        # the error response never reflects request data back to the client.
        safe_errors = [
            {k: v for k, v in err.items() if k in ("type", "loc", "msg")}
            for err in exc.errors()
        ]
        return _problem(422, "Request validation failed.", extra={"errors": safe_errors})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Never leak internals to the client; log the full error with the id.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _problem(500, "An unexpected error occurred.")
