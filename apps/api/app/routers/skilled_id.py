"""
SKILLED ID — B2B credential-verification API.

Authorized partners (job boards, staffing agencies, background-check firms) query
a worker's VERIFIED credential status. Three gates apply to every request:

  1. Authentication  — X-API-Key header → hashed lookup in api_clients.
  2. Rate limiting   — per-partner sliding window by subscription tier (Redis).
  3. Consent         — only data categories the worker explicitly opted to share
                       with THIS requester category are ever returned.

Every call is logged to api_request_logs for audit + per-query metering/billing.
Only verification_level >= INSTITUTION_VERIFIED is returned — the product is
*verified* status, not self-reported claims.

See docs/skilled-pro/03-skilled-id-api.md.
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel

from app.db import get_db
from app.skilled_pro import apikeys, keyring
from app.skilled_pro.consent import RequesterCategory, parse_external_sharing
from app.skilled_pro.ratelimit import TIERS, InMemoryBackend, RateLimiter, RedisBackend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skilled-id/v1", tags=["skilled-id"])

# Map a data category to the credential fields it governs. The verify endpoint
# concerns "certifications" (credentials); other categories are reserved.
CREDENTIAL_CATEGORY = "certifications"


# ---------------------------------------------------------------------------
# Rate limiter (Redis in prod; in-memory fallback if Redis is unreachable)
# ---------------------------------------------------------------------------

def _build_limiter() -> RateLimiter:
    try:
        import redis  # type: ignore

        from app.config import get_settings
        client = redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
        client.ping()
        return RateLimiter(RedisBackend(client))
    except Exception as exc:  # pragma: no cover - depends on infra
        logger.warning("SKILLED ID rate limiter falling back to in-memory: %s", exc)
        return RateLimiter(InMemoryBackend())


_limiter: Optional[RateLimiter] = None


def _limiter_instance() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _build_limiter()
    return _limiter


# ---------------------------------------------------------------------------
# Partner authentication
# ---------------------------------------------------------------------------

class ApiClient(BaseModel):
    id: str
    name: str
    requester_category: str
    tier: str


async def authenticate_partner(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> ApiClient:
    if not x_api_key:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    prefix = apikeys.prefix_of(x_api_key)
    if not prefix:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed API key")

    async with get_db() as conn:
        row = await conn.fetchrow(
            "SELECT id::text AS id, name, requester_category, tier, key_hash, active "
            "FROM public.api_clients WHERE key_prefix = $1",
            prefix,
        )
        if not row or not row["active"]:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or inactive API key")
        if not apikeys.verify_key(x_api_key, row["key_hash"], keyring.get_api_key_pepper()):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        await conn.execute(
            "UPDATE public.api_clients SET last_used_at = now() WHERE id = $1", row["id"]
        )
    return ApiClient(
        id=row["id"], name=row["name"],
        requester_category=row["requester_category"], tier=row["tier"],
    )


def _enforce_rate_limit(client: ApiClient, response: Response, *, bulk: bool = False) -> None:
    tier = TIERS.get("bulk" if bulk else client.tier, TIERS["free"])
    decision = _limiter_instance().check(f"{client.id}:{tier.name}", tier)
    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    response.headers["X-RateLimit-Reset"] = str(decision.reset_seconds)
    if not decision.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit exceeded",
            headers={"Retry-After": str(decision.reset_seconds)},
        )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class VerifiedCredential(BaseModel):
    canonical_code: Optional[str]
    canonical_name: Optional[str]
    credential_type: Optional[str]
    issuer: Optional[str]
    verification_level: int
    verification_badge: str
    expires_date: Optional[str]


class VerifyResult(BaseModel):
    subject_id: str
    found: bool
    consented: bool
    credentials: list[VerifiedCredential]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

async def _verify_subject(
    conn: asyncpg.Connection, subject_id: str, requester: RequesterCategory
) -> VerifyResult:
    appl = await conn.fetchrow(
        "SELECT id::text AS id FROM public.applicants WHERE id = $1", subject_id
    )
    if not appl:
        return VerifyResult(subject_id=subject_id, found=False, consented=False, credentials=[])

    # Consent gate: is this requester category permitted to receive certifications?
    cs = await conn.fetchrow(
        "SELECT external_sharing FROM public.consent_settings "
        "WHERE applicant_id = $1 AND data_category = $2",
        subject_id, CREDENTIAL_CATEGORY,
    )
    allowed = requester in parse_external_sharing(cs["external_sharing"] if cs else [])
    if not allowed:
        return VerifyResult(subject_id=subject_id, found=True, consented=False, credentials=[])

    rows = await conn.fetch(
        "SELECT canonical_code, canonical_name, credential_type, issuer, "
        "       verification_level, expires_date "
        "FROM public.credentials "
        "WHERE applicant_id = $1 AND verification_level >= 1 "
        "ORDER BY verification_level DESC",
        subject_id,
    )
    from app.skilled_pro.verification import VerificationLevel
    creds = [
        VerifiedCredential(
            canonical_code=r["canonical_code"],
            canonical_name=r["canonical_name"],
            credential_type=r["credential_type"],
            issuer=r["issuer"],
            verification_level=r["verification_level"],
            verification_badge=VerificationLevel(r["verification_level"]).badge,
            expires_date=r["expires_date"].isoformat() if r["expires_date"] else None,
        )
        for r in rows
    ]
    return VerifyResult(subject_id=subject_id, found=True, consented=True, credentials=creds)


async def _log_request(conn, client_id: str, endpoint: str, subject_count: int, code: int):
    await conn.execute(
        "INSERT INTO public.api_request_logs "
        "(api_client_id, endpoint, subject_count, status_code) VALUES ($1,$2,$3,$4)",
        client_id, endpoint, subject_count, code,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/verify", response_model=VerifyResult)
async def verify_one(
    subject_id: str,
    response: Response,
    client: Annotated[ApiClient, Depends(authenticate_partner)],
):
    _enforce_rate_limit(client, response)
    requester = RequesterCategory(client.requester_category) \
        if client.requester_category in RequesterCategory._value2member_map_ \
        else RequesterCategory.OTHER
    async with get_db() as conn:
        result = await _verify_subject(conn, subject_id, requester)
        await _log_request(conn, client.id, "verify", 1, 200)
    return result


class BulkVerifyIn(BaseModel):
    subject_ids: list[str]


@router.post("/verify/bulk", response_model=list[VerifyResult])
async def verify_bulk(
    body: BulkVerifyIn,
    response: Response,
    client: Annotated[ApiClient, Depends(authenticate_partner)],
):
    if len(body.subject_ids) > 500:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Max 500 subjects per bulk request")
    _enforce_rate_limit(client, response, bulk=True)
    requester = RequesterCategory(client.requester_category) \
        if client.requester_category in RequesterCategory._value2member_map_ \
        else RequesterCategory.OTHER
    results: list[VerifyResult] = []
    async with get_db() as conn:
        for sid in body.subject_ids:
            results.append(await _verify_subject(conn, sid, requester))
        await _log_request(conn, client.id, "verify/bulk", len(body.subject_ids), 200)
    return results
