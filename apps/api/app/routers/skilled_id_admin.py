"""
SKILLED ID Partner Console (admin).

Operationalizes the B2B credential-verification API: issue / rotate / revoke
partner API keys, manage subscription tiers, view per-partner usage analytics
(for the per-query billing model), and run a consent-gated live test from the
console. Raw keys are shown exactly once at issue/rotate; only the SHA-256 hash
is stored. Every key-lifecycle action is written to audit_logs.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, require_admin
from app.db import get_db
from app.skilled_pro import apikeys, keyring
from app.skilled_pro.consent import RequesterCategory
from app.skilled_pro.ratelimit import TIERS
from app.skilled_pro.usage import fill_daily_series
from app.routers.skilled_id import VerifyResult, _verify_subject

router = APIRouter(prefix="/admin/skilled-id", tags=["skilled-id-admin"])

_TIERS = ("free", "standard", "premium", "bulk")
_REQUESTERS = tuple(c.value for c in RequesterCategory)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PartnerOut(BaseModel):
    id: str
    name: str
    contact_email: Optional[str]
    requester_category: str
    tier: str
    key_prefix: str
    active: bool
    created_at: str
    last_used_at: Optional[str]
    total_requests: int
    requests_30d: int
    rate_limit: int


class PartnerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_email: Optional[str] = Field(default=None, max_length=200)
    requester_category: str = "other"
    tier: str = "free"
    live: bool = True


class PartnerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    contact_email: Optional[str] = Field(default=None, max_length=200)
    requester_category: Optional[str] = None
    tier: Optional[str] = None
    active: Optional[bool] = None


class KeyIssued(BaseModel):
    partner: PartnerOut
    api_key: str          # shown ONCE — never retrievable again


class UsagePoint(BaseModel):
    date: str
    count: int


class EndpointCount(BaseModel):
    endpoint: str
    count: int


class RecentRequest(BaseModel):
    endpoint: str
    subject_count: int
    status_code: int
    created_at: str


class UsageReport(BaseModel):
    total_requests: int
    total_subjects: int
    requests_30d: int
    last_used_at: Optional[str]
    daily: list[UsagePoint]
    by_endpoint: list[EndpointCount]
    recent: list[RecentRequest]


class TestRequest(BaseModel):
    api_client_id: str
    subject_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_tier(tier: str) -> None:
    if tier not in _TIERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"tier must be one of {_TIERS}")


def _validate_requester(req: str) -> None:
    if req not in _REQUESTERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"requester_category must be one of {_REQUESTERS}")


def _partner_out(row: asyncpg.Record) -> PartnerOut:
    tier = row["tier"]
    return PartnerOut(
        id=str(row["id"]),
        name=row["name"],
        contact_email=row["contact_email"],
        requester_category=row["requester_category"],
        tier=tier,
        key_prefix=row["key_prefix"],
        active=row["active"],
        created_at=row["created_at"].isoformat(),
        last_used_at=row["last_used_at"].isoformat() if row["last_used_at"] else None,
        total_requests=int(row["total_requests"]),
        requests_30d=int(row["requests_30d"]),
        rate_limit=TIERS.get(tier, TIERS["free"]).limit,
    )


_LIST_SELECT = """
    SELECT c.id, c.name, c.contact_email, c.requester_category, c.tier,
           c.key_prefix, c.active, c.created_at, c.last_used_at,
           (SELECT count(*) FROM public.api_request_logs l WHERE l.api_client_id = c.id) AS total_requests,
           (SELECT count(*) FROM public.api_request_logs l WHERE l.api_client_id = c.id
              AND l.created_at >= now() - interval '30 days') AS requests_30d
    FROM public.api_clients c
"""


async def _audit(conn, user: CurrentUser, action: str, entity_id: str, after: dict | None = None):
    await conn.execute(
        "INSERT INTO public.audit_logs (actor_id, actor_role, action, entity_type, entity_id, after_state) "
        "VALUES ($1::uuid, $2, $3, 'api_client', $4::uuid, $5)",
        user.user_id, user.role, action, entity_id, after,
    )


async def _new_unique_key(conn, live: bool):
    """Generate an API key whose prefix is unique (retry on the rare collision)."""
    pepper = keyring.get_api_key_pepper()
    for _ in range(5):
        gk = apikeys.generate_api_key(live=live, pepper=pepper)
        exists = await conn.fetchval(
            "SELECT 1 FROM public.api_clients WHERE key_prefix = $1", gk.prefix
        )
        if not exists:
            return gk
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not allocate a unique key")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/clients", response_model=list[PartnerOut])
async def list_partners(user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        rows = await conn.fetch(_LIST_SELECT + " ORDER BY c.created_at DESC")
    return [_partner_out(r) for r in rows]


@router.post("/clients", response_model=KeyIssued, status_code=status.HTTP_201_CREATED)
async def create_partner(body: PartnerCreate, user: Annotated[CurrentUser, Depends(require_admin)]):
    _validate_tier(body.tier)
    _validate_requester(body.requester_category)
    async with get_db() as conn:
        gk = await _new_unique_key(conn, body.live)
        await conn.execute(
            """
            INSERT INTO public.api_clients
                (name, contact_email, requester_category, tier, key_prefix, key_hash, active)
            VALUES ($1,$2,$3,$4,$5,$6,true)
            """,
            body.name, body.contact_email, body.requester_category, body.tier,
            gk.prefix, gk.key_hash,
        )
        row = await conn.fetchrow(_LIST_SELECT + " WHERE c.key_prefix = $1", gk.prefix)
        await _audit(conn, user, "api_client.create", str(row["id"]),
                     {"name": body.name, "tier": body.tier, "requester_category": body.requester_category})
    return KeyIssued(partner=_partner_out(row), api_key=gk.raw)


@router.post("/clients/{client_id}/rotate", response_model=KeyIssued)
async def rotate_key(client_id: str, user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        existing = await conn.fetchrow("SELECT id, key_prefix FROM public.api_clients WHERE id = $1::uuid", client_id)
        if not existing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")
        gk = await _new_unique_key(conn, live=True)
        await conn.execute(
            "UPDATE public.api_clients SET key_prefix = $2, key_hash = $3 WHERE id = $1::uuid",
            client_id, gk.prefix, gk.key_hash,
        )
        row = await conn.fetchrow(_LIST_SELECT + " WHERE c.id = $1::uuid", client_id)
        await _audit(conn, user, "api_client.rotate_key", client_id, {"old_prefix": existing["key_prefix"]})
    return KeyIssued(partner=_partner_out(row), api_key=gk.raw)


@router.patch("/clients/{client_id}", response_model=PartnerOut)
async def update_partner(client_id: str, body: PartnerUpdate, user: Annotated[CurrentUser, Depends(require_admin)]):
    if body.tier is not None:
        _validate_tier(body.tier)
    if body.requester_category is not None:
        _validate_requester(body.requester_category)

    sets: list[str] = []
    params: list[Any] = []
    for field in ("name", "contact_email", "requester_category", "tier", "active"):
        val = getattr(body, field)
        if val is not None:
            params.append(val)
            sets.append(f"{field} = ${len(params)}")
    if not sets:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

    params.append(client_id)
    async with get_db() as conn:
        updated = await conn.fetchval(
            f"UPDATE public.api_clients SET {', '.join(sets)} WHERE id = ${len(params)}::uuid RETURNING id",
            *params,
        )
        if not updated:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")
        row = await conn.fetchrow(_LIST_SELECT + " WHERE c.id = $1::uuid", client_id)
        await _audit(conn, user, "api_client.update", client_id, body.model_dump(exclude_none=True))
    return _partner_out(row)


@router.get("/clients/{client_id}/usage", response_model=UsageReport)
async def partner_usage(client_id: str, user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        exists = await conn.fetchval("SELECT 1 FROM public.api_clients WHERE id = $1::uuid", client_id)
        if not exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")

        totals = await conn.fetchrow(
            "SELECT count(*) AS total, COALESCE(sum(subject_count),0) AS subjects, max(created_at) AS last_used "
            "FROM public.api_request_logs WHERE api_client_id = $1::uuid",
            client_id,
        )
        recent_30 = await conn.fetchval(
            "SELECT count(*) FROM public.api_request_logs WHERE api_client_id = $1::uuid "
            "AND created_at >= now() - interval '30 days'",
            client_id,
        )
        day_rows = await conn.fetch(
            "SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day, count(*) AS n "
            "FROM public.api_request_logs WHERE api_client_id = $1::uuid "
            "AND created_at >= now() - interval '30 days' GROUP BY 1",
            client_id,
        )
        ep_rows = await conn.fetch(
            "SELECT endpoint, count(*) AS n FROM public.api_request_logs "
            "WHERE api_client_id = $1::uuid GROUP BY endpoint ORDER BY n DESC",
            client_id,
        )
        recent_rows = await conn.fetch(
            "SELECT endpoint, subject_count, status_code, created_at FROM public.api_request_logs "
            "WHERE api_client_id = $1::uuid ORDER BY created_at DESC LIMIT 10",
            client_id,
        )

    daily = fill_daily_series({r["day"]: r["n"] for r in day_rows}, days=30, today=date.today())
    return UsageReport(
        total_requests=int(totals["total"]),
        total_subjects=int(totals["subjects"]),
        requests_30d=int(recent_30),
        last_used_at=totals["last_used"].isoformat() if totals["last_used"] else None,
        daily=[UsagePoint(**p) for p in daily],
        by_endpoint=[EndpointCount(endpoint=r["endpoint"], count=int(r["n"])) for r in ep_rows],
        recent=[
            RecentRequest(
                endpoint=r["endpoint"], subject_count=r["subject_count"],
                status_code=r["status_code"], created_at=r["created_at"].isoformat(),
            )
            for r in recent_rows
        ],
    )


@router.post("/test", response_model=VerifyResult)
async def test_verify(body: TestRequest, user: Annotated[CurrentUser, Depends(require_admin)]):
    """Run a consent-gated verify as the selected partner — for onboarding/QA.
    Does not consume the partner's rate limit or billing (it's an admin console test)."""
    async with get_db() as conn:
        client = await conn.fetchrow(
            "SELECT requester_category FROM public.api_clients WHERE id = $1::uuid", body.api_client_id
        )
        if not client:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")
        requester = (
            RequesterCategory(client["requester_category"])
            if client["requester_category"] in RequesterCategory._value2member_map_
            else RequesterCategory.OTHER
        )
        return await _verify_subject(conn, body.subject_id, requester)
