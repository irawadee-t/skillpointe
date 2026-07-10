"""
Employer Verified-Worker Directory + SKILLED Verify.

Lets an employer discover and verify workers who hold SKILLED-verified
credentials — but ONLY workers who explicitly consented to share their
certifications with employers (see skilled_pro.discovery for the invariants).

Surfaces are data-minimized: identity + trade + verified credentials only.
Contact details are never returned here (separate consent + the messaging flow).
Every per-candidate verification is logged to engagement_events for audit +
the existing employer analytics. Admins may view read-only (no employer action
is recorded for them).
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser, require_employer_or_admin
from app.db import get_db
from app.skilled_pro.discovery import (
    GATED_CATEGORY,
    MIN_VERIFIED_LEVEL,
    employer_may_access,
)
from app.skilled_pro.verification import VerificationLevel
from app.skilled_pro import ranking

router = APIRouter(prefix="/employer/me/verified-workers", tags=["verified-workers"])

# The discovery gate, applied identically in search and verify. 'employer' and
# the level are constants (not user input), so they're inlined safely.
_DISCOVERABLE = (
    "EXISTS (SELECT 1 FROM public.consent_settings cs "
    "        WHERE cs.applicant_id = a.id AND cs.data_category = 'certifications' "
    "          AND cs.external_sharing ? 'employer') "
    "AND EXISTS (SELECT 1 FROM public.credentials cv "
    f"           WHERE cv.applicant_id = a.id AND cv.verification_level >= {MIN_VERIFIED_LEVEL})"
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VerifiedCredentialBrief(BaseModel):
    canonical_code: Optional[str]
    canonical_name: Optional[str]
    verification_level: int
    verification_badge: str


class WorkerCard(BaseModel):
    applicant_id: str
    name: str
    city: Optional[str]
    state: Optional[str]
    trade: Optional[str]
    available_from: Optional[str]
    willing_to_relocate: bool
    verified_count: int
    relevance: float = 0.0
    top_credentials: list[VerifiedCredentialBrief]


class SearchFacets(BaseModel):
    trades: list[dict[str, str]]        # {code, name}
    credentials: list[dict[str, str]]   # {code, name}


class SearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    workers: list[WorkerCard]
    facets: SearchFacets


class VerifiedCredentialFull(BaseModel):
    canonical_code: Optional[str]
    canonical_name: Optional[str]
    credential_type: Optional[str]
    issuer: Optional[str]
    verification_level: int
    verification_badge: str
    issued_date: Optional[str]
    expires_date: Optional[str]


class VerifyResponse(BaseModel):
    applicant_id: str
    name: str
    city: Optional[str]
    state: Optional[str]
    trade: Optional[str]
    verified_count: int
    credentials: list[VerifiedCredentialFull]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _employer_id_or_none(conn: asyncpg.Connection, user: CurrentUser) -> Optional[str]:
    """Employer's id for audit logging; None for admins (who view read-only)."""
    if user.role == "admin":
        return None
    return await conn.fetchval(
        "SELECT employer_id::text FROM public.employer_contacts WHERE user_id = $1 LIMIT 1",
        user.user_id,
    )


def _full_name(first: Any, last: Any, fallback: str = "Unnamed") -> str:
    return " ".join(p for p in [first, last] if p) or fallback


def _brief(rows: list[dict[str, Any]]) -> list[VerifiedCredentialBrief]:
    out = []
    for r in rows or []:
        lvl = int(r["verification_level"])
        out.append(VerifiedCredentialBrief(
            canonical_code=r.get("canonical_code"),
            canonical_name=r.get("canonical_name"),
            verification_level=lvl,
            verification_badge=VerificationLevel(lvl).badge,
        ))
    return out


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.get("", response_model=SearchResponse)
async def search_verified_workers(
    user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
    state: Optional[str] = Query(default=None, max_length=2),
    trade: Optional[str] = Query(default=None, max_length=120),
    credential: Optional[str] = Query(default=None, max_length=120),
    q: Optional[str] = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=50),
):
    conditions = [_DISCOVERABLE]
    params: list[Any] = []

    if state:
        params.append(state.upper())
        conditions.append(f"a.state = ${len(params)}")
    if trade:
        params.append(trade)
        conditions.append(f"jf.code = ${len(params)}")
    if credential:
        params.append(credential)
        conditions.append(
            f"EXISTS (SELECT 1 FROM public.credentials cf WHERE cf.applicant_id = a.id "
            f"        AND cf.canonical_code = ${len(params)} AND cf.verification_level >= {MIN_VERIFIED_LEVEL})"
        )

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    join = "LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id"

    async with get_db() as conn:
        total = await conn.fetchval(
            f"SELECT count(*) FROM public.applicants a {join} WHERE {where}", *params
        )

        # Fetch the discoverable+filtered set, then rank in Python (hybrid:
        # credentials + recency + free-text query). The discoverable set is small.
        rows = await conn.fetch(
            f"""
            SELECT a.id::text AS id, a.first_name, a.last_name, a.city, a.state,
                   jf.code AS trade_code, jf.name AS trade_name,
                   a.available_from_date, a.willing_to_relocate,
                   EXTRACT(DAY FROM (now() - a.updated_at))::int AS days_since_active,
                   (SELECT count(*) FROM public.credentials c
                      WHERE c.applicant_id = a.id AND c.verification_level >= {MIN_VERIFIED_LEVEL})
                     AS verified_count,
                   (SELECT jsonb_agg(t) FROM (
                       SELECT c.canonical_name, c.canonical_code, c.verification_level
                       FROM public.credentials c
                       WHERE c.applicant_id = a.id AND c.verification_level >= {MIN_VERIFIED_LEVEL}
                       ORDER BY c.verification_level DESC, c.updated_at DESC
                       LIMIT 3
                   ) t) AS top_credentials
            FROM public.applicants a {join}
            WHERE {where}
            ORDER BY verified_count DESC, a.updated_at DESC NULLS LAST
            LIMIT 200
            """,
            *params,
        )

        # Facets over the full discoverable set (no optional filters), for UI dropdowns.
        trade_rows = await conn.fetch(
            f"SELECT DISTINCT jf.code AS code, jf.name AS name "
            f"FROM public.applicants a "
            f"JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id "
            f"WHERE {_DISCOVERABLE} AND jf.code IS NOT NULL ORDER BY 2"
        )
        cred_rows = await conn.fetch(
            f"SELECT DISTINCT c.canonical_code AS code, c.canonical_name AS name "
            f"FROM public.credentials c JOIN public.applicants a ON a.id = c.applicant_id "
            f"WHERE {_DISCOVERABLE} AND c.verification_level >= {MIN_VERIFIED_LEVEL} "
            f"  AND c.canonical_code IS NOT NULL ORDER BY 2"
        )

    scored: list[WorkerCard] = []
    for r in rows:
        briefs = _brief(r["top_credentials"])
        relevance = ranking.relevance_score(
            verified_count=int(r["verified_count"]),
            days_since_active=r["days_since_active"],
            q=q,
            trade=r["trade_name"],
            credential_names=[b.canonical_name or "" for b in briefs],
        )
        scored.append(WorkerCard(
            applicant_id=r["id"],
            name=_full_name(r["first_name"], r["last_name"]),
            city=r["city"],
            state=r["state"],
            trade=r["trade_name"],
            available_from=r["available_from_date"].isoformat() if r["available_from_date"] else None,
            willing_to_relocate=bool(r["willing_to_relocate"]),
            verified_count=int(r["verified_count"]),
            relevance=relevance,
            top_credentials=briefs,
        ))

    # Hybrid ranking: relevance desc, then verified_count desc as tiebreak.
    scored.sort(key=lambda w: (w.relevance, w.verified_count), reverse=True)
    offset = (page - 1) * page_size
    workers = scored[offset:offset + page_size]
    facets = SearchFacets(
        trades=[{"code": r["code"], "name": r["name"] or r["code"]} for r in trade_rows],
        credentials=[{"code": r["code"], "name": r["name"] or r["code"]} for r in cred_rows],
    )
    return SearchResponse(total=int(total), page=page, page_size=page_size, workers=workers, facets=facets)


# ---------------------------------------------------------------------------
# SKILLED Verify (per candidate)
# ---------------------------------------------------------------------------

@router.get("/{applicant_id}", response_model=VerifyResponse)
async def verify_worker(
    applicant_id: str,
    user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
):
    async with get_db() as conn:
        appl = await conn.fetchrow(
            "SELECT a.id::text AS id, a.first_name, a.last_name, a.city, a.state, "
            "       jf.name AS trade "
            "FROM public.applicants a "
            "LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id "
            "WHERE a.id = $1",
            applicant_id,
        )
        if not appl:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Worker not found")

        # Consent gate — identical rule to search, enforced via the pure predicate.
        sharing = await conn.fetchval(
            "SELECT external_sharing FROM public.consent_settings "
            "WHERE applicant_id = $1 AND data_category = $2",
            applicant_id, GATED_CATEGORY,
        )
        if not employer_may_access(sharing):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "This worker has not consented to share verified credentials with employers.",
            )

        rows = await conn.fetch(
            f"""
            SELECT canonical_code, canonical_name, credential_type, issuer,
                   verification_level, issued_date, expires_date
            FROM public.credentials
            WHERE applicant_id = $1 AND verification_level >= {MIN_VERIFIED_LEVEL}
            ORDER BY verification_level DESC, updated_at DESC
            """,
            applicant_id,
        )

        # Audit: log the verification as an employer action (not for admins).
        employer_id = await _employer_id_or_none(conn, user)
        if employer_id is not None:
            await conn.execute(
                "INSERT INTO public.engagement_events "
                "(applicant_id, employer_id, event_type, event_data) "
                "VALUES ($1, $2, 'candidate_verified', $3)",
                applicant_id, employer_id,
                {"verified_count": len(rows), "via": "skilled_verify"},
            )

    creds = [
        VerifiedCredentialFull(
            canonical_code=r["canonical_code"],
            canonical_name=r["canonical_name"],
            credential_type=r["credential_type"],
            issuer=r["issuer"],
            verification_level=int(r["verification_level"]),
            verification_badge=VerificationLevel(int(r["verification_level"])).badge,
            issued_date=r["issued_date"].isoformat() if r["issued_date"] else None,
            expires_date=r["expires_date"].isoformat() if r["expires_date"] else None,
        )
        for r in rows
    ]
    return VerifyResponse(
        applicant_id=appl["id"],
        name=_full_name(appl["first_name"], appl["last_name"]),
        city=appl["city"],
        state=appl["state"],
        trade=appl["trade"],
        verified_count=len(creds),
        credentials=creds,
    )
