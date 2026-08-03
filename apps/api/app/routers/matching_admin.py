"""
matching_admin.py — Admin matching-configuration API (Phase 9).

The matching engine reads its ScoringConfig from the active policy_configs
row (SCORING_CONFIG.yaml is the code-default fallback). This router lets an
admin view, dry-run, and activate a new config:

  GET  /admin/matching/config    — active config + history + recompute status
  POST /admin/matching/preview   — dry-run a candidate config on a sample,
                                   server-side, BEFORE committing: eligible /
                                   near-fit deltas + top-10 old-vs-new for
                                   spotlight applicants
  POST /admin/matching/activate  — versioned policy_configs row (history is
                                   never overwritten) + audit_logs row +
                                   global recompute trigger

Guardrails:
  - require_admin on everything; every mutation writes audit_logs
  - relaxation tiers change VISIBILITY only — never base_fit_score
  - base_fit_score and policy_adjusted_score stay separate
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import require_admin
from app.auth.schemas import CurrentUser
from app.db import get_db
from app.util.audit import write_audit

# packages/ import path (matching engine is pure python, no DB I/O inside).
# Walk only existing parents: the deploy layout can be flatter than the repo
# (Railway Root Directory = apps/api), where parents[4] does not exist.
for _parent in Path(__file__).resolve().parents:
    _pkg = _parent / "packages"
    if _pkg.is_dir():
        if str(_pkg) not in sys.path:
            sys.path.insert(0, str(_pkg))
        break

# Every endpoint here needs the matching engine. When packages/ is not shipped
# with the deploy, keep the rest of the API alive and fail these routes with a
# clear message instead of crashing the whole app at import.
try:
    from matching.config import (  # noqa: E402
        _from_yaml,
        config_to_dict,
        load_config,
        normalize_weights,
        validate_config_dict,
    )
    from matching.engine import compute_match  # noqa: E402

    MATCHING_AVAILABLE = True
except ImportError:  # pragma: no cover - deploy-layout dependent
    _from_yaml = config_to_dict = load_config = None  # type: ignore[assignment]
    normalize_weights = validate_config_dict = compute_match = None  # type: ignore[assignment]
    MATCHING_AVAILABLE = False

logger = logging.getLogger(__name__)


def _require_matching_engine() -> None:
    """Guard every route in this router; see the import block above."""
    if not MATCHING_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                "The matching engine is not available in this deployment. "
                "Ship the packages/ directory with the API to enable matching "
                "configuration."
            ),
        )


router = APIRouter(
    prefix="/admin/matching",
    tags=["admin"],
    dependencies=[Depends(_require_matching_engine)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PreviewRequest(BaseModel):
    config: dict[str, Any]
    sample_size: int = Field(default=20, ge=3, le=60)
    spotlight_applicant_ids: list[str] = Field(default_factory=list, max_length=5)
    normalize: bool = False   # scale weights to 100 before validating


class ActivateRequest(BaseModel):
    config: dict[str, Any]
    note: str = Field(min_length=3, max_length=500)
    normalize: bool = False


# ---------------------------------------------------------------------------
# Shared fetch helpers (asyncpg mirrors of scripts/recompute_matches.py)
# ---------------------------------------------------------------------------

_APPLICANT_SQL = """
    SELECT
        a.id, a.first_name, a.last_name, a.program_name_raw,
        a.state, a.region, a.city,
        a.willing_to_relocate, a.willing_to_travel, a.commute_radius_miles,
        a.lat, a.lng,
        a.experience_raw, a.bio_raw, a.career_goals_raw,
        a.expected_completion_date, a.available_from_date,
        a.travel_preference::text, a.relocation_preference::text,
        a.relocation_states,
        a.has_internship, a.internship_details,
        a.essay_background, a.essay_impact,
        a.enrollment_status::text, a.career_path, a.program_field,
        jf.code AS canonical_job_family_code,
        a.degree_type::text, a.school_name, a.specific_career
    FROM public.applicants a
    LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
"""

_JOBS_SQL = """
    SELECT
        j.id, j.employer_id,
        j.title_raw, j.title_normalized, j.description_raw,
        j.requirements_raw, j.preferred_qualifications_raw,
        j.state, j.region, j.city, j.lat, j.lng,
        j.work_setting::text, j.travel_requirement,
        j.pay_min, j.pay_max, j.pay_type::text,
        j.required_credentials, j.experience_level,
        jf.code AS canonical_job_family_code,
        j.required_experience_years
    FROM public.jobs j
    LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
    WHERE j.is_active = TRUE
"""


def _row_to_dict(row) -> dict[str, Any]:
    d = dict(row)
    # asyncpg Decimal → float for the pure engine
    for k, v in d.items():
        if hasattr(v, "as_integer_ratio") and not isinstance(v, (int, float)):
            d[k] = float(v)
    return d


async def _fetch_active_config_dict(conn) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return (complete config dict, active row meta or None).

    Parsing the stored JSON through ScoringConfig and re-serializing fills
    any missing new sections with code defaults — the admin UI always sees a
    complete, current-schema config.
    """
    row = await conn.fetchrow(
        """
        SELECT id::text, version, description, config,
               activated_at::text, activated_by::text, created_at::text
        FROM public.policy_configs WHERE is_active = TRUE LIMIT 1
        """
    )
    if row:
        raw = row["config"]
        raw = raw if isinstance(raw, dict) else json.loads(raw)
        cfg = _from_yaml(raw)
        meta = {
            "id": row["id"], "version": row["version"],
            "description": row["description"],
            "activated_at": row["activated_at"], "created_at": row["created_at"],
        }
        return config_to_dict(cfg), meta
    return config_to_dict(load_config()), None


# ---------------------------------------------------------------------------
# GET /admin/matching/config
# ---------------------------------------------------------------------------

@router.get("/config")
async def get_matching_config(
    current_user: Annotated[CurrentUser, Depends(require_admin)],
) -> dict[str, Any]:
    """Active matching config (complete, current-schema), version history,
    latest recompute run, and the live match distribution."""
    async with get_db() as conn:
        config, active_meta = await _fetch_active_config_dict(conn)

        history = [
            dict(r) for r in await conn.fetch(
                """
                SELECT version, description, is_active,
                       created_at::text, activated_at::text, deactivated_at::text
                FROM public.policy_configs
                ORDER BY created_at DESC LIMIT 15
                """
            )
        ]

        last_run = await conn.fetchrow(
            """
            SELECT kind, status, started_at::text, completed_at::text, error
            FROM public.recompute_runs
            ORDER BY created_at DESC LIMIT 1
            """
        )

        dist = await conn.fetchrow(
            """
            SELECT
              COUNT(*)                                                    AS total,
              COUNT(*) FILTER (WHERE eligibility_status = 'eligible')     AS eligible,
              COUNT(*) FILTER (WHERE eligibility_status = 'near_fit')     AS near_fit,
              COUNT(*) FILTER (WHERE match_tier = 'nearby')               AS nearby_tier,
              COUNT(DISTINCT applicant_id) FILTER (WHERE match_tier IS NOT NULL) AS applicants_with_any_tier
            FROM public.matches
            """
        )

    return {
        "config": config,
        "active": active_meta,
        "history": history,
        "last_recompute": dict(last_run) if last_run else None,
        "distribution": dict(dist) if dist else None,
    }


# ---------------------------------------------------------------------------
# GET /admin/matching/recompute-status — poll target after activation
# ---------------------------------------------------------------------------

@router.get("/recompute-status")
async def recompute_status(
    current_user: Annotated[CurrentUser, Depends(require_admin)],
) -> dict[str, Any]:
    """Latest recompute run, for the activate/recompute progress poller.
    Includes elapsed seconds and the current match total so the UI can show
    honest progress ('running for 42s') and surface errors instead of
    pretending completion."""
    async with get_db() as conn:
        run = await conn.fetchrow(
            """
            SELECT id::text, kind, status, error,
                   started_at, completed_at, created_at
            FROM public.recompute_runs
            ORDER BY created_at DESC LIMIT 1
            """
        )
        matches_total = await conn.fetchval("SELECT COUNT(*) FROM public.matches")
    if not run:
        return {"run": None, "matches_total": int(matches_total or 0)}
    from datetime import datetime, timezone
    started = run["started_at"]
    completed = run["completed_at"]
    elapsed = None
    if started:
        end = completed or datetime.now(timezone.utc)
        elapsed = int((end - started).total_seconds())
    return {
        "run": {
            "id": run["id"], "kind": run["kind"], "status": run["status"],
            "error": run["error"],
            "started_at": started.isoformat() if started else None,
            "completed_at": completed.isoformat() if completed else None,
            "elapsed_seconds": elapsed,
        },
        "matches_total": int(matches_total or 0),
    }


# ---------------------------------------------------------------------------
# POST /admin/matching/preview  — server-side dry run on a sample
# ---------------------------------------------------------------------------

def _compute_sample(
    applicants: list[dict], jobs: list[dict], employers: dict[str, dict],
    raw_config: dict[str, Any],
) -> dict[str, dict]:
    """Pure compute: {applicant_id: {counts, top}} under the candidate config."""
    cfg = _from_yaml(raw_config)
    out: dict[str, dict] = {}
    today = date.today()
    for app in applicants:
        counts = {"eligible": 0, "near_fit": 0, "nearby": 0}
        scored: list[tuple[float, dict]] = []
        for job in jobs:
            emp = employers.get(str(job.get("employer_id")), {})
            try:
                r = compute_match(app, job, emp, cfg, today=today)
            except Exception:
                continue
            if r.eligibility_status in ("eligible", "near_fit"):
                counts[r.eligibility_status] += 1
            if r.match_tier == "nearby":
                counts["nearby"] += 1
            if r.match_tier is not None:
                scored.append((
                    r.policy_adjusted_score,
                    {
                        "job_id": str(job["id"]),
                        "job_title": job.get("title_normalized") or job.get("title_raw"),
                        "city": job.get("city"), "state": job.get("state"),
                        "score": r.policy_adjusted_score,
                        "base_fit_score": r.base_fit_score,
                        "eligibility_status": r.eligibility_status,
                        "match_label": r.match_label,
                        "match_tier": r.match_tier,
                        "tier_reason": r.tier_reason,
                        "distance_miles": r.distance_miles,
                    },
                ))
        # Deterministic ordering: score desc, then distance asc, then job id
        scored.sort(key=lambda t: (
            -t[0],
            t[1]["distance_miles"] if t[1]["distance_miles"] is not None else 1e9,
            t[1]["job_id"],
        ))
        # Tier-honest top-10: strict/adjacent/stretch first, nearby only after
        tier_rank = {"strict": 0, "adjacent": 1, "stretch": 2, "nearby": 3}
        scored.sort(key=lambda t: tier_rank.get(t[1]["match_tier"], 9))
        out[str(app["id"])] = {"counts": counts, "top": [s[1] for s in scored[:10]]}
    return out


@router.post("/preview")
async def preview_matching_config(
    body: PreviewRequest,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
) -> dict[str, Any]:
    """Dry-run a candidate config server-side on a deterministic sample of
    applicants x all active jobs. Nothing is written; the response shows the
    admin the consequences (eligible/near-fit deltas, spotlight top-10 old vs
    new) before activation."""
    raw = dict(body.config)
    if body.normalize:
        weights = (raw.get("structured_score") or {}).get("weights") or {}
        if weights:
            raw.setdefault("structured_score", {})["weights"] = normalize_weights(weights)

    errors = validate_config_dict(raw)
    if errors:
        raise HTTPException(status_code=422, detail="Invalid config: " + "; ".join(errors))

    async with get_db() as conn:
        # Deterministic stratified-ish sample: md5 ordering is stable run-to-run
        sample_rows = await conn.fetch(
            _APPLICANT_SQL + " ORDER BY md5(a.id::text) LIMIT $1", body.sample_size
        )
        applicants = [_row_to_dict(r) for r in sample_rows]

        # Spotlight applicants (always included)
        if body.spotlight_applicant_ids:
            have = {str(a["id"]) for a in applicants}
            missing = [i for i in body.spotlight_applicant_ids if i not in have]
            if missing:
                extra = await conn.fetch(
                    _APPLICANT_SQL + " WHERE a.id = ANY($1::uuid[])", missing
                )
                applicants.extend(_row_to_dict(r) for r in extra)

        jobs = [_row_to_dict(r) for r in await conn.fetch(_JOBS_SQL)]
        employers = {
            str(r["id"]): dict(r)
            for r in await conn.fetch("SELECT id, name, is_partner FROM public.employers")
        }
        total_applicants = await conn.fetchval("SELECT COUNT(*) FROM public.applicants")

        app_ids = [str(a["id"]) for a in applicants]
        old_rows = await conn.fetch(
            """
            SELECT m.applicant_id::text AS applicant_id, m.job_id::text AS job_id,
                   m.eligibility_status::text, m.match_label::text, m.match_tier,
                   m.tier_reason, m.policy_adjusted_score, m.base_fit_score,
                   m.distance_miles,
                   COALESCE(j.title_normalized, j.title_raw) AS job_title,
                   j.city, j.state
            FROM public.matches m
            JOIN public.jobs j ON j.id = m.job_id
            WHERE m.applicant_id = ANY($1::uuid[])
            """,
            app_ids,
        )

    # Old-side aggregation from the live matches table
    old: dict[str, dict] = {i: {"counts": {"eligible": 0, "near_fit": 0, "nearby": 0}, "top": []} for i in app_ids}
    for r in old_rows:
        rec = old.get(r["applicant_id"])
        if rec is None:
            continue
        if r["eligibility_status"] in ("eligible", "near_fit"):
            rec["counts"][r["eligibility_status"]] += 1
        if r["match_tier"] == "nearby":
            rec["counts"]["nearby"] += 1
        if r["eligibility_status"] in ("eligible", "near_fit") or r["match_tier"] == "nearby":
            rec["top"].append({
                "job_id": r["job_id"], "job_title": r["job_title"],
                "city": r["city"], "state": r["state"],
                "score": float(r["policy_adjusted_score"] or 0),
                "base_fit_score": float(r["base_fit_score"] or 0),
                "eligibility_status": r["eligibility_status"],
                "match_label": r["match_label"],
                "match_tier": r["match_tier"], "tier_reason": r["tier_reason"],
                "distance_miles": float(r["distance_miles"]) if r["distance_miles"] is not None else None,
            })
    tier_rank = {"strict": 0, "adjacent": 1, "stretch": 2, "nearby": 3, None: 4}
    for rec in old.values():
        rec["top"].sort(key=lambda t: (
            tier_rank.get(t["match_tier"], 9), -t["score"],
            t["distance_miles"] if t["distance_miles"] is not None else 1e9, t["job_id"],
        ))
        rec["top"] = rec["top"][:10]

    # New-side: pure compute, off the event loop
    new = await asyncio.to_thread(_compute_sample, applicants, jobs, employers, raw)

    def _totals(side: dict[str, dict]) -> dict[str, int]:
        t = {"eligible": 0, "near_fit": 0, "nearby": 0, "applicants_with_results": 0}
        for rec in side.values():
            for k in ("eligible", "near_fit", "nearby"):
                t[k] += rec["counts"][k]
            if sum(rec["counts"].values()) > 0:
                t["applicants_with_results"] += 1
        return t

    spotlight_ids = body.spotlight_applicant_ids or app_ids[:3]
    name_by_id = {
        str(a["id"]): (f"{a.get('first_name') or ''} {a.get('last_name') or ''}".strip()
                       or str(a["id"])[:8])
        for a in applicants
    }
    family_by_id = {str(a["id"]): a.get("canonical_job_family_code") for a in applicants}
    spotlight = [
        {
            "applicant_id": i,
            "name": name_by_id.get(i, i[:8]),
            "family": family_by_id.get(i),
            "old": old.get(i, {"counts": {}, "top": []}),
            "new": new.get(i, {"counts": {}, "top": []}),
        }
        for i in spotlight_ids if i in new
    ]

    return {
        "sample_applicants": len(applicants),
        "total_applicants": int(total_applicants or 0),
        "jobs": len(jobs),
        "old_totals": _totals(old),
        "new_totals": _totals(new),
        "spotlight": spotlight,
        "note": (
            "Sampled dry run: totals cover the sampled applicants only; "
            "activation recomputes every pair."
        ),
    }


# ---------------------------------------------------------------------------
# POST /admin/matching/activate
# ---------------------------------------------------------------------------

@router.post("/activate", status_code=201)
async def activate_matching_config(
    body: ActivateRequest,
    current_user: Annotated[CurrentUser, Depends(require_admin)],
) -> dict[str, Any]:
    """Activate a new matching config: versioned policy_configs row (history
    preserved), audit_logs row, and a global recompute trigger."""
    raw = dict(body.config)
    if body.normalize:
        weights = (raw.get("structured_score") or {}).get("weights") or {}
        if weights:
            raw.setdefault("structured_score", {})["weights"] = normalize_weights(weights)

    errors = validate_config_dict(raw)
    if errors:
        raise HTTPException(status_code=422, detail="Invalid config: " + "; ".join(errors))

    # Canonicalize: parse → serialize fills defaults + normalizes weights, so
    # the stored row is always a complete, current-schema config.
    canonical = config_to_dict(_from_yaml(raw))

    async with get_db() as conn:
        async with conn.transaction():
            before_cfg, before_meta = await _fetch_active_config_dict(conn)

            # Next version: v<max+1> over numeric versions (v1, v2, ...)
            versions = [r["version"] for r in await conn.fetch(
                "SELECT version FROM public.policy_configs"
            )]
            nums = [int(m.group(1)) for v in versions if (m := re.match(r"^v(\d+)$", v or ""))]
            version = f"v{(max(nums) + 1) if nums else 2}"
            canonical["version"] = version

            await conn.execute(
                """
                UPDATE public.policy_configs
                SET is_active = FALSE, deactivated_at = NOW()
                WHERE is_active = TRUE
                """
            )
            new_row = await conn.fetchrow(
                """
                INSERT INTO public.policy_configs
                    (version, is_active, config, description,
                     created_by, activated_by, activated_at)
                -- $2 is a JSON text param cast text->jsonb so the stored value
                -- is a jsonb OBJECT. A bare $2::jsonb makes asyncpg's jsonb
                -- codec wrap the string as a jsonb string scalar, which breaks
                -- every config->'...' path lookup downstream.
                VALUES ($1, TRUE, $2::text::jsonb, $3, $4::uuid, $4::uuid, NOW())
                RETURNING id::text, version, activated_at::text
                """,
                version, json.dumps(canonical), body.note, current_user.user_id,
            )

            await write_audit(
                conn,
                action="matching_config_activated",
                actor_id=current_user.user_id,
                actor_role="admin",
                entity_type="policy_config",
                entity_id=new_row["id"],
                before={"version": (before_meta or {}).get("version"), "config": before_cfg},
                after={"version": version, "config": canonical},
                metadata={"note": body.note},
            )

    # Global recompute — reuses the locked scheduler path (safe vs cron overlap)
    from app.worker.scheduler import _locked_recompute
    asyncio.create_task(_locked_recompute())

    return {
        "activated": True,
        "version": new_row["version"],
        "policy_config_id": new_row["id"],
        "activated_at": new_row["activated_at"],
        "recompute_started": True,
        "detail": (
            "Config activated. A full recompute has started. Scores and tiers "
            "update as it completes (progress under recompute runs)."
        ),
    }
