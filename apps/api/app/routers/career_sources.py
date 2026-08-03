"""
Employer "Connect careers page" — self-serve careers-URL pipeline.

  • /employer/me/career-source        — save/list/delete connected URLs
  • /employer/me/career-source/pull   — pull (or re-pull) jobs from the site
  • /employer/me/career-source/pulls  — pull history (found/new/updated/…)
  • /admin/career-sources             — admin visibility + pull on behalf

Pulls sync into the source's rolling job_import_batches batch, so every job
flows through the SAME approval pipeline (and job_display_sections
normalization) as every other import. Admin sharing follows the CLAUDE.md
rule: check is_admin FIRST and never call the employer-contact resolver for
admin sessions.
"""
from __future__ import annotations

import logging
import time as _time
from typing import Annotated, Any, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.dependencies import (
    CurrentUser,
    get_current_user,
    require_admin,
    require_employer_or_admin,
)
from app.db import get_db
from app.skilled_pro.career_sources import run_pull
from app.skilled_pro.ratelimit import RateTier
from app.util.audit import write_audit
from app.util.net_guard import BlockedURLError, validate_public_url
from app.util.rate_limit import _limiter_instance

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/employer/me/career-source", tags=["career-sources"])
adm_router = APIRouter(prefix="/admin/career-sources", tags=["career-sources-admin"])

# One pull at a time with a few minutes of cooldown: 2 pulls / 5 min / user.
PULL_TIER = RateTier(name="career_pull", limit=2, window=300)


async def _rate_limit_pull(user: CurrentUser = Depends(get_current_user)) -> None:
    try:
        decision = _limiter_instance().check(f"career_pull:{user.user_id}", PULL_TIER)
    except Exception:  # pragma: no cover — fail open like the LLM tier
        return
    if not decision.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"A pull just ran. Try again in {max(1, decision.reset_seconds // 60)} minute(s).",
            headers={"Retry-After": str(decision.reset_seconds)},
        )


async def _rate_limit_admin_pull(
    source_id: str, user: CurrentUser = Depends(get_current_user),
) -> None:
    """Admin pulls are limited PER SOURCE, not per admin user — an operator
    working through twelve different employers' sources isn't hammering any
    one site, and the per-user 2/5min limit made that routine work impossible.
    The per-source key still protects each employer's careers page from
    repeated hits."""
    try:
        decision = _limiter_instance().check(f"career_pull:src:{source_id}", PULL_TIER)
    except Exception:  # pragma: no cover — fail open like the LLM tier
        return
    if not decision.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "This source was just pulled. Try again in "
                f"{max(1, decision.reset_seconds // 60)} minute(s)."
            ),
            headers={"Retry-After": str(decision.reset_seconds)},
        )


# ============================================================================
# Schemas
# ============================================================================

class SourceIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)


class SourceOut(BaseModel):
    id: str
    employer_id: str
    url: str
    platform: Optional[str] = None
    batch_id: Optional[str] = None
    last_pulled_at: Optional[str] = None
    last_status: Optional[str] = None
    last_error: Optional[str] = None
    jobs_found: int = 0
    created_at: str
    # Learned-profile + auto-sync state
    has_profile: bool = False
    auto_sync_enabled: bool = True
    auto_sync_interval_hours: int = 6
    next_auto_sync_at: Optional[str] = None
    consecutive_failures: int = 0
    # Parked for a human: a sync's removal set was too large to apply blind.
    needs_attention: bool = False
    attention_reason: Optional[str] = None
    attention_at: Optional[str] = None


class SourceSettingsIn(BaseModel):
    auto_sync_enabled: Optional[bool] = None
    auto_sync_interval_hours: Optional[int] = Field(default=None, ge=1, le=168)


class PullIn(BaseModel):
    source_id: Optional[str] = None
    max_jobs: int = Field(default=200, ge=1, le=500)
    # 'auto' reuses the learned profile (instant incremental); 'full' forces
    # a from-scratch discovery + relearn.
    mode: str = Field(default="auto", pattern="^(auto|full)$")


class PullOut(BaseModel):
    pull_id: Optional[str] = None
    batch_id: Optional[str] = None
    status: str
    platform: Optional[str] = None
    error: Optional[str] = None
    jobs_found: int = 0
    jobs_new: int = 0
    jobs_updated: int = 0
    jobs_removed: int = 0
    jobs_rejected: int = 0
    links_broken: int = 0
    # Sync-activity metadata
    sync_mode: str = "full"          # full | incremental | not_modified | relearned
    duration_ms: Optional[int] = None
    fetch_count: Optional[int] = None
    details: dict[str, Any] = Field(default_factory=dict)
    # Did this pull see the WHOLE listing, and what did it do about removals?
    # applied | skipped_incomplete | held_for_review | not_applicable
    listing_complete: Optional[bool] = None
    removal_detection: Optional[str] = None


class PullHistoryItem(PullOut):
    created_at: str
    triggered_by: Optional[str] = None   # null = scheduled auto-sync


# ============================================================================
# Helpers
# ============================================================================

async def _resolve_employer_id(
    conn: asyncpg.Connection, user: CurrentUser, employer_id: Optional[str] = None,
) -> str:
    """Admin sessions pass ?employer_id explicitly; employers resolve via
    employer_contacts. Per CLAUDE.md, is_admin is checked FIRST."""
    if user.role == "admin":
        if not employer_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Admins must pass employer_id")
        return employer_id
    row = await conn.fetchrow(
        "SELECT employer_id::text AS id FROM public.employer_contacts WHERE user_id = $1 LIMIT 1",
        user.user_id,
    )
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No employer linked to this account")
    return row["id"]


def _source_out(r: asyncpg.Record) -> dict[str, Any]:
    keys = tuple(r.keys())   # Record.keys() is an iterator — materialize it
    return {
        "id": str(r["id"]),
        "employer_id": str(r["employer_id"]),
        "url": r["url"],
        "platform": r["platform"],
        "batch_id": str(r["batch_id"]) if r["batch_id"] else None,
        "last_pulled_at": r["last_pulled_at"].isoformat() if r["last_pulled_at"] else None,
        "last_status": r["last_status"],
        "last_error": r["last_error"],
        "jobs_found": r["jobs_found"],
        "created_at": r["created_at"].isoformat(),
        "has_profile": bool(r["extraction_profile"]) if "extraction_profile" in keys else False,
        "auto_sync_enabled": bool(r["auto_sync_enabled"]) if "auto_sync_enabled" in keys else True,
        "auto_sync_interval_hours": r["auto_sync_interval_hours"]
        if "auto_sync_interval_hours" in keys else 6,
        "next_auto_sync_at": r["next_auto_sync_at"].isoformat()
        if "next_auto_sync_at" in keys and r["next_auto_sync_at"] else None,
        "consecutive_failures": r["consecutive_failures"]
        if "consecutive_failures" in keys else 0,
        "needs_attention": bool(r["needs_attention"])
        if "needs_attention" in keys else False,
        "attention_reason": r["attention_reason"] if "attention_reason" in keys else None,
        "attention_at": r["attention_at"].isoformat()
        if "attention_at" in keys and r["attention_at"] else None,
    }


def _pull_out(r: asyncpg.Record) -> dict[str, Any]:
    keys = tuple(r.keys())   # Record.keys() is an iterator — materialize it
    details = r["details"] if "details" in keys else {}
    if isinstance(details, str):
        import json as _json
        try:
            details = _json.loads(details)
        except _json.JSONDecodeError:
            details = {}
    return {
        "pull_id": str(r["id"]),
        "batch_id": str(r["batch_id"]) if r["batch_id"] else None,
        "status": r["status"],
        "platform": r["platform"],
        "error": r["error"],
        "jobs_found": r["jobs_found"],
        "jobs_new": r["jobs_new"],
        "jobs_updated": r["jobs_updated"],
        "jobs_removed": r["jobs_removed"],
        "jobs_rejected": r["jobs_rejected"],
        "links_broken": r["links_broken"],
        "sync_mode": (r["sync_mode"] if "sync_mode" in keys else None) or "full",
        "duration_ms": r["duration_ms"] if "duration_ms" in keys else None,
        "fetch_count": r["fetch_count"] if "fetch_count" in keys else None,
        "details": details or {},
        "listing_complete": r["listing_complete"] if "listing_complete" in keys else None,
        "removal_detection": r["removal_detection"] if "removal_detection" in keys else None,
        "created_at": r["created_at"].isoformat(),
        "triggered_by": str(r["triggered_by"]) if r["triggered_by"] else None,
    }


async def _load_source(conn, employer_id: str, source_id: Optional[str]) -> asyncpg.Record:
    if source_id:
        rec = await conn.fetchrow(
            "SELECT s.*, e.name AS employer_name FROM public.employer_career_sources s "
            "JOIN public.employers e ON e.id = s.employer_id "
            "WHERE s.id = $1::uuid AND s.employer_id = $2::uuid",
            source_id, employer_id,
        )
    else:
        rec = await conn.fetchrow(
            "SELECT s.*, e.name AS employer_name FROM public.employer_career_sources s "
            "JOIN public.employers e ON e.id = s.employer_id "
            "WHERE s.employer_id = $1::uuid ORDER BY s.created_at DESC LIMIT 1",
            employer_id,
        )
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "No careers page connected yet. Save a URL first.")
    return rec


# ============================================================================
# Employer endpoints (admin may act with ?employer_id=…)
# ============================================================================

@router.get("", response_model=list[SourceOut])
async def list_sources(
    user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
    employer_id: Optional[str] = None,
):
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user, employer_id)
        rows = await conn.fetch(
            "SELECT * FROM public.employer_career_sources WHERE employer_id = $1::uuid "
            "ORDER BY created_at DESC", emp_id,
        )
        return [_source_out(r) for r in rows]


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
async def save_source(
    body: SourceIn,
    user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
    employer_id: Optional[str] = None,
):
    """Connect a careers-page URL. The link is validated (scheme + SSRF guard)
    before it is stored; platform detection is best-effort and refreshed on
    every pull."""
    url = body.url.strip()
    try:
        validate_public_url(url)
    except BlockedURLError as exc:
        # Human copy only — the guard's technical reason goes to the log.
        logger.info("Career-source URL rejected by the outbound guard: %s (%s)", url, exc)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "We can't reach that address. Use your public careers page URL.",
        ) from exc

    from scraper.platform import detect_from_url  # type: ignore

    platform = detect_from_url(url).value
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user, employer_id)
        rec = await conn.fetchrow(
            """
            INSERT INTO public.employer_career_sources
                (employer_id, url, platform, created_by,
                 auto_sync_enabled, next_auto_sync_at)
            -- New sources hold in a "couldn't connect yet" state: auto-sync
            -- stays OFF until the first pull that finds ≥1 job (run_pull
            -- flips it on). A URL that never works must never keep syncing.
            VALUES ($1::uuid, $2, $3, $4::uuid, FALSE, NULL)
            ON CONFLICT (employer_id, url) DO UPDATE SET updated_at = now()
            RETURNING *
            """,
            emp_id, url, platform if platform != "unknown" else None, user.user_id,
        )
        await write_audit(
            conn, action="career_source_saved",
            actor_id=user.user_id, actor_role=user.role,
            entity_type="employer_career_sources", entity_id=str(rec["id"]),
            after={"url": url, "platform": platform},
            metadata={"employer_id": emp_id},
        )
        return _source_out(rec)


@router.delete("/{source_id}")
async def delete_source(
    source_id: str,
    user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
    employer_id: Optional[str] = None,
):
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user, employer_id)
        deleted = await conn.fetchval(
            "DELETE FROM public.employer_career_sources "
            "WHERE id = $1::uuid AND employer_id = $2::uuid RETURNING id",
            source_id, emp_id,
        )
        if not deleted:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
        return {"ok": True}


@router.post("/pull", response_model=PullOut, dependencies=[Depends(_rate_limit_pull)])
async def pull_source(
    body: PullIn,
    user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
    employer_id: Optional[str] = None,
):
    """Pull (or re-pull) jobs from the connected careers page. Re-pulls dedupe
    on the posting URL: existing rows refresh in place, new postings stage for
    review, vanished postings go stale."""
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user, employer_id)
        rec = await _load_source(conn, emp_id, body.source_id)
        source = dict(rec)
        started = _time.monotonic()
        result = await run_pull(conn, source, triggered_by=user.user_id,
                                max_jobs=body.max_jobs, force_full=body.mode == "full")
        await write_audit(
            conn, action="career_source_pull",
            actor_id=user.user_id, actor_role=user.role,
            entity_type="employer_career_sources", entity_id=str(rec["id"]),
            after={k: v for k, v in result.items() if k != "error"},
            metadata={"employer_id": emp_id, "duration_s": round(_time.monotonic() - started, 1)},
        )
        return result


@router.get("/pulls", response_model=list[PullHistoryItem])
async def pull_history(
    user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
    employer_id: Optional[str] = None,
    source_id: Optional[str] = None,
):
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user, employer_id)
        rows = await conn.fetch(
            """
            SELECT p.* FROM public.career_source_pulls p
            JOIN public.employer_career_sources s ON s.id = p.source_id
            WHERE s.employer_id = $1::uuid
              AND ($2::uuid IS NULL OR p.source_id = $2::uuid)
            ORDER BY p.created_at DESC LIMIT 50
            """,
            emp_id, source_id,
        )
        return [_pull_out(r) for r in rows]


@router.patch("/{source_id}", response_model=SourceOut)
async def update_source_settings(
    source_id: str,
    body: SourceSettingsIn,
    user: Annotated[CurrentUser, Depends(require_employer_or_admin)],
    employer_id: Optional[str] = None,
):
    """Auto-sync settings: on/off + how often (hours). Audited."""
    if body.auto_sync_enabled is None and body.auto_sync_interval_hours is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to update")
    async with get_db() as conn:
        emp_id = await _resolve_employer_id(conn, user, employer_id)
        rec = await conn.fetchrow(
            """
            UPDATE public.employer_career_sources SET
                auto_sync_enabled = COALESCE($3, auto_sync_enabled),
                auto_sync_interval_hours = COALESCE($4, auto_sync_interval_hours),
                next_auto_sync_at = CASE
                    WHEN COALESCE($3, auto_sync_enabled) IS FALSE THEN NULL
                    ELSE now() + make_interval(hours => COALESCE($4, auto_sync_interval_hours))
                END,
                -- An explicit employer setting resets churn-based adaptation:
                -- their choice is the new base until churn says otherwise.
                no_change_streak = CASE WHEN $4 IS NULL THEN no_change_streak ELSE 0 END,
                adaptive_interval_hours = CASE WHEN $4 IS NULL
                                               THEN adaptive_interval_hours ELSE NULL END,
                updated_at = now()
            WHERE id = $1::uuid AND employer_id = $2::uuid
            RETURNING *
            """,
            source_id, emp_id, body.auto_sync_enabled, body.auto_sync_interval_hours,
        )
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
        await write_audit(
            conn, action="career_source_settings",
            actor_id=user.user_id, actor_role=user.role,
            entity_type="employer_career_sources", entity_id=source_id,
            after={"auto_sync_enabled": rec["auto_sync_enabled"],
                   "auto_sync_interval_hours": rec["auto_sync_interval_hours"]},
            metadata={"employer_id": emp_id},
        )
        return _source_out(rec)


# ============================================================================
# Admin endpoints
# ============================================================================

@adm_router.get("")
async def admin_list_sources(
    user: Annotated[CurrentUser, Depends(require_admin)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """All connected sources with health: last sync, live/staged/held job
    counts, next auto-sync, failure streak, and the last pull's broken-link /
    held detail — the ops console listing. Paginated with a real total."""
    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT s.*, e.name AS employer_name,
                   (SELECT count(*) FROM public.job_import_rows r
                     WHERE r.batch_id = s.batch_id AND r.status = 'published') AS jobs_published,
                   (SELECT count(*) FROM public.job_import_rows r
                     WHERE r.batch_id = s.batch_id AND r.status = 'staged') AS jobs_staged,
                   (SELECT count(*) FROM public.job_import_rows r
                     WHERE r.batch_id = s.batch_id AND r.status = 'held') AS jobs_held,
                   lp.links_broken AS last_links_broken,
                   lp.jobs_rejected AS last_jobs_rejected,
                   lp.details AS last_pull_details,
                   count(*) OVER () AS _total
              FROM public.employer_career_sources s
              JOIN public.employers e ON e.id = s.employer_id
              LEFT JOIN LATERAL (
                  SELECT p.links_broken, p.jobs_rejected, p.details
                    FROM public.career_source_pulls p
                   WHERE p.source_id = s.id
                   ORDER BY p.created_at DESC LIMIT 1
              ) lp ON TRUE
             ORDER BY s.last_pulled_at DESC NULLS LAST
             LIMIT $1 OFFSET $2
            """,
            limit, offset,
        )
        total = int(rows[0]["_total"]) if rows else 0

        def _details(raw: Any) -> dict:
            if isinstance(raw, dict):
                return raw
            if isinstance(raw, str):
                import json as _json
                try:
                    return _json.loads(raw)
                except _json.JSONDecodeError:
                    return {}
            return {}

        items = [
            {
                **_source_out(r),
                "employer_name": r["employer_name"],
                "jobs_published": r["jobs_published"] or 0,
                "jobs_staged": r["jobs_staged"] or 0,
                "jobs_held": r["jobs_held"] or 0,
                "last_links_broken": int(r["last_links_broken"] or 0),
                "last_jobs_rejected": int(r["last_jobs_rejected"] or 0),
                # e.g. {"held": [urls...]} from the link checker — computed by
                # every pull; now actually visible to the operator.
                "last_pull_details": _details(r["last_pull_details"]),
            }
            for r in rows
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}


class PullHistoryOut(BaseModel):
    items: list[PullHistoryItem]
    total: int
    limit: int
    offset: int


@adm_router.get("/{source_id}/pulls", response_model=PullHistoryOut)
async def admin_pull_history(
    source_id: str, user: Annotated[CurrentUser, Depends(require_admin)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Per-source sync activity timeline (same shape the employer sees)."""
    async with get_db() as conn:
        rows = await conn.fetch(
            "SELECT p.*, count(*) OVER () AS _total FROM public.career_source_pulls p "
            "WHERE p.source_id = $1::uuid ORDER BY p.created_at DESC "
            "LIMIT $2 OFFSET $3",
            source_id, limit, offset,
        )
        total = int(rows[0]["_total"]) if rows else 0
        return {"items": [_pull_out(r) for r in rows], "total": total,
                "limit": limit, "offset": offset}


@adm_router.post("/reconcile")
async def admin_reconcile_legacy_jobs(
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    """Enroll pre-career-sources scraped/imported jobs into each registered
    source's fingerprint memory (matched by URL: learned link patterns →
    listing host → Workday tenant → registrable domain) so the NEXT listing
    sync governs their lifecycle. Jobs matching no source stay orphans and
    remain covered by the apply-link recheck. Idempotent; audited."""
    from app.skilled_pro.reconcile import reconcile_legacy_jobs

    async with get_db() as conn:
        result = await reconcile_legacy_jobs(conn)
        await write_audit(
            conn, action="career_source_reconcile",
            actor_id=user.user_id, actor_role=user.role,
            entity_type="employer_career_sources", entity_id=None,
            after={k: v for k, v in result.items() if k != "orphans_by_host"},
            metadata={"orphans_by_host": result.get("orphans_by_host", {})},
        )
        return result


@adm_router.post("/{source_id}/pull", response_model=PullOut,
                 dependencies=[Depends(_rate_limit_admin_pull)])
async def admin_pull(source_id: str, user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        rec = await conn.fetchrow(
            "SELECT s.*, e.name AS employer_name FROM public.employer_career_sources s "
            "JOIN public.employers e ON e.id = s.employer_id WHERE s.id = $1::uuid",
            source_id,
        )
        if not rec:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
        result = await run_pull(conn, dict(rec), triggered_by=user.user_id)
        await write_audit(
            conn, action="career_source_pull",
            actor_id=user.user_id, actor_role=user.role,
            entity_type="employer_career_sources", entity_id=source_id,
            after={k: v for k, v in result.items() if k != "error"},
            metadata={"employer_id": str(rec["employer_id"]), "by": "admin"},
        )
        return result
