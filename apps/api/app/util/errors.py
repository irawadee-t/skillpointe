"""
Consistent error envelope (RFC 7807 problem+json).

Every error response gets the same shape — status, a machine-readable title, a
human detail, and the request's correlation id — so first-party clients and the
B2B partner API integrate against one contract instead of ad-hoc strings. Register
with ``install_error_handlers(app)``.
"""
from __future__ import annotations

import logging

import httpx
from asyncpg.exceptions import DataError, ForeignKeyViolationError, UniqueViolationError
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError as _PydValidationError
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

    @app.exception_handler(_PydValidationError)
    async def _pyd_validation(request: Request, exc: _PydValidationError):
        # A pydantic model built INSIDE a handler from external data (an
        # uploaded CSV row, an LLM extraction) failed validation — FastAPI's
        # RequestValidationError handler only covers models bound at the
        # request boundary, so this would otherwise 500. A malformed input row
        # is the client's, so it is a 422. Field values are not echoed.
        logger.info("In-handler validation failure on %s %s",
                    request.method, request.url.path)
        return _problem(422, "Some submitted data was not in a valid format.")

    @app.exception_handler(httpx.HTTPError)
    async def _httpx_error(request: Request, exc: httpx.HTTPError):
        # An outbound call to a third party (credential verifier, background
        # check, scraper) failed at the transport level — a network/timeout
        # problem on THEIR side, not a bug on ours. Surface a clean 502 so the
        # client can retry, instead of a 500 that reads as our fault.
        logger.warning("Upstream call failed on %s %s: %s",
                       request.method, request.url.path, type(exc).__name__)
        return _problem(502, "An upstream service did not respond. Please try again.")

    @app.exception_handler(UniqueViolationError)
    async def _pg_unique_error(request: Request, exc: UniqueViolationError):
        # A duplicate insert that raced a read-then-check (e.g. two concurrent
        # submits of a one-per-record action) — the record already exists, so
        # this is a 409, never a 500.
        logger.info("Rejected duplicate insert on %s %s",
                    request.method, request.url.path)
        return _problem(409, "That item already exists.")

    @app.exception_handler(ForeignKeyViolationError)
    async def _pg_fk_error(request: Request, exc: ForeignKeyViolationError):
        # A write referencing a row that does not exist (e.g. a conversation
        # started against a deleted job/applicant from a stale client) — the
        # referenced entity is gone, so this is a 409/404-class client error,
        # never a 500. No internal detail is echoed.
        logger.info("Rejected FK violation on %s %s",
                    request.method, request.url.path)
        return _problem(409, "A referenced item no longer exists.")

    @app.exception_handler(DataError)
    async def _pg_data_error(request: Request, exc: DataError):
        # asyncpg raises DataError for malformed inputs that reach a raw SQL
        # cast — e.g. a non-UUID string in a "$1::uuid" path param, or a value
        # outside an enum. That is a client mistake (bad path/query value), not
        # a server fault, so it must be a clean 422, never a 500. The specific
        # value is never echoed back.
        logger.info("Rejected malformed input on %s %s: %s",
                    request.method, request.url.path, type(exc).__name__)
        return _problem(422, "A value in the request was not a valid format.")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Never leak internals to the client; log the full error with the id.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _problem(500, "An unexpected error occurred.")