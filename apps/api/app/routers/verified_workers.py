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

from datetime import date
from typing import Annotated, Any, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser, require_employer_or_admin
from app.db import get_db
from app.skilled_pro import ranking
from app.skilled_pro.discovery import (
    GATED_CATEGORY,
    MIN_VERIFIED_LEVEL,
    employer_may_access,
)
from app.skilled_pro.geocode import geocode
from app.skilled_pro.verification import VerificationLevel
from app.util.filters import csv_values
from app.util.suggest import SuggestResponse, cap_groups, fetch_label_suggestions

router = APIRouter(prefix="/employer/me/verified-workers", tags=["verified-workers"])

# The discovery gate, applied identically in search and verify. 'employer' and
# the level are constants (not user input), so they're inlined safely.
_DISCOVERABLE = (
    "EXISTS (SELECT 1 FROM public.consent_settings cs "
    "        WHERE cs.applicant_id = a.id AND cs.data_category = 'certifications' "
    "          AND cs.external_sharing ? 'employer') "
    "AND EXISTS (SELECT 1 FROM public.credentials cv "
    f"           WHERE cv.applicant_id = a.id AND cv.verification_level >= {MIN_VERIFIED_LEVEL}) "
    # Minor protection: under-18 applicants are not proactively surfaced to
    # employers. NULL DOB (unknown age) is treated as an adult.
    "AND (a.date_of_birth IS NULL OR a.date_of_birth <= CURRENT_DATE - INTERVAL '18 years')"
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
    last_active_days: Optional[int] = None
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

# Mirrors matching.geo.DEFAULT_COMMUTE_RADIUS_MILES (the API deliberately does
# not import packages/matching — same convention as skilled_pro/commute.py).
_DEFAULT_RADIUS_MILES = 50.0
_EARTH_RADIUS_MILES = 3958.8

# The credential-category taxonomy (jobs + credentials share these values).
_CREDENTIAL_TYPES = {"certification", "license", "degree", "apprenticeship", "safety", "union"}


@router.get("", response_model=SearchResponse)
async def search_verified_workers(
    user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
    state: Optional[str] = Query(default=None, max_length=2),
    trade: Optional[str] = Query(default=None, max_length=120, description="Single trade code (back-compat)"),
    trades: Optional[str] = Query(default=None, max_length=600, description="Comma-separated trade codes"),
    credential: Optional[str] = Query(default=None, max_length=120),
    credential_types: Optional[str] = Query(
        default=None, max_length=200,
        description="Comma-separated categories: certification|license|degree|apprenticeship|safety|union",
    ),
    min_level: Optional[int] = Query(
        default=None, ge=1, le=2,
        description="Highest verification held: 1=institution-verified, 2=SKILLED-verified",
    ),
    available_by: Optional[str] = Query(
        default=None, description="Available on/before YYYY-MM-DD ('now' = today)",
    ),
    relocate: Optional[bool] = Query(default=None, description="Willing to relocate"),
    near_city: Optional[str] = Query(default=None, max_length=120,
                                     description="City — workers whose stated commute radius reaches it"),
    near_state: Optional[str] = Query(default=None, max_length=2),
    active_within_days: Optional[int] = Query(default=None, ge=1, le=3650,
                                              description="Profile updated within N days"),
    q: Optional[str] = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=50),
):
    # The consent + verified + adult gate comes FIRST and is part of every
    # query below — added filters can only narrow the discoverable set, never
    # widen it (tested in tests/test_granular_worker_filters.py).
    conditions = [_DISCOVERABLE]
    params: list[Any] = []

    if state:
        params.append(state.upper())
        conditions.append(f"a.state = ${len(params)}")
    trade_list = csv_values(trades) or ([trade] if trade else [])
    if trade_list:
        params.append(trade_list)
        conditions.append(f"jf.code = ANY(${len(params)}::text[])")
    if credential:
        params.append(credential)
        conditions.append(
            f"EXISTS (SELECT 1 FROM public.credentials cf WHERE cf.applicant_id = a.id "
            f"        AND cf.canonical_code = ${len(params)} AND cf.verification_level >= {MIN_VERIFIED_LEVEL})"
        )
    type_list = csv_values(credential_types)
    if type_list:
        bad = [t for t in type_list if t not in _CREDENTIAL_TYPES]
        if bad:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"credential_types must be within: {', '.join(sorted(_CREDENTIAL_TYPES))}",
            )
        params.append(type_list)
        conditions.append(
            f"EXISTS (SELECT 1 FROM public.credentials ct WHERE ct.applicant_id = a.id "
            f"        AND ct.credential_type = ANY(${len(params)}::text[]) "
            f"        AND ct.verification_level >= {MIN_VERIFIED_LEVEL})"
        )
    if min_level is not None:
        params.append(min_level)
        conditions.append(
            f"EXISTS (SELECT 1 FROM public.credentials cl WHERE cl.applicant_id = a.id "
            f"        AND cl.verification_level >= ${len(params)})"
        )
    if available_by:
        target = date.today() if available_by == "now" else None
        if target is None:
            try:
                target = date.fromisoformat(available_by)
            except ValueError:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    "available_by must be 'now' or YYYY-MM-DD")
        params.append(target)
        conditions.append(
            f"(a.available_from_date IS NULL OR a.available_from_date <= ${len(params)})"
        )
    if relocate is not None:
        params.append(relocate)
        conditions.append(f"COALESCE(a.willing_to_relocate, FALSE) = ${len(params)}")
    if active_within_days is not None:
        params.append(active_within_days)
        conditions.append(f"a.updated_at >= now() - make_interval(days => ${len(params)})")

    offset = (page - 1) * page_size

    join = "LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id"

    async with get_db() as conn:
        if near_city:
            # Reachability = the point sits inside the worker's own stated
            # commute radius (default 50 mi when unset), around the worker's
            # geocoded home. Server-side haversine — no matching-package import.
            point = await geocode(conn, city=near_city, state=near_state or "")
            if point is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    f"Could not locate city: {near_city}")
            lat, lng = point
            params.append(lat)
            lat_ph = f"${len(params)}"
            params.append(lng)
            lng_ph = f"${len(params)}"
            conditions.append(
                "(a.lat IS NOT NULL AND a.lng IS NOT NULL AND "
                f"2 * {_EARTH_RADIUS_MILES} * asin(sqrt("
                f"power(sin(radians((a.lat - {lat_ph}) / 2)), 2) + "
                f"cos(radians({lat_ph})) * cos(radians(a.lat)) * "
                f"power(sin(radians((a.lng - {lng_ph}) / 2)), 2)"
                f")) <= COALESCE(NULLIF(a.commute_radius_miles, 0), {_DEFAULT_RADIUS_MILES}))"
            )

        where = " AND ".join(conditions)

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
            last_active_days=r["days_since_active"],
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
# GET /employer/me/verified-workers/suggest — keyword dropdown
# (registered BEFORE /{applicant_id} so "suggest" never binds as an id)
# ---------------------------------------------------------------------------

@router.get("/suggest", response_model=SuggestResponse)
async def suggest_verified_workers(
    user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
    q: str = Query(..., min_length=1, max_length=120),
):
    """Credential names + trade names matching `q` — the two things the
    keyword search actually ranks by.

    Every source row carries the SAME consent + verified + adult gate as the
    search itself (`_DISCOVERABLE`), so the dropdown can never leak a
    credential or trade held only by non-consented workers (isolation is
    asserted in tests/test_suggest_endpoints.py).
    """
    async with get_db() as conn:
        credentials = await fetch_label_suggestions(
            conn,
            kind="credential",
            label_expr="c.canonical_name",
            from_clause=(
                "FROM public.credentials c "
                "JOIN public.applicants a ON a.id = c.applicant_id"
            ),
            where=f"{_DISCOVERABLE} AND c.verification_level >= {MIN_VERIFIED_LEVEL}",
            q=q,
            limit=8,
        )
        trades = await fetch_label_suggestions(
            conn,
            kind="trade",
            label_expr="jf.name",
            from_clause=(
                "FROM public.canonical_job_families jf "
                "JOIN public.applicants a ON a.canonical_job_family_id = jf.id"
            ),
            where=_DISCOVERABLE,
            q=q,
            limit=8,
        )
    return SuggestResponse(suggestions=cap_groups([credentials, trades]))


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
