"""
applicants.py — Applicant-facing API endpoints (Phase 6.1).

All routes require an authenticated applicant (require_applicant dep).
Data is fetched via asyncpg using raw SQL for complex JOINs.

Endpoints:
  GET /applicant/me/profile         — profile summary for dashboard header
  GET /applicant/me/matches         — ranked jobs (two sections: eligible + near_fit)
  GET /applicant/me/matches/{id}    — full match detail + dimension scores

DECISIONS.md guardrails:
  - policy_adjusted_score is the display score (separate from base_fit_score)
  - Ineligible matches hidden from applicant (is_visible_to_applicant = TRUE enforced)
  - Geography is included in every response
  - RBAC enforced: only the authenticated applicant sees their own data
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import require_applicant
from app.auth.schemas import CurrentUser
from app.db import get_db
from app.schemas.applicant import (
    ApplicantProfileSummary,
    DimensionScoreItem,
    GateResultItem,
    JobMatchDetail,
    JobMatchSummary,
    PolicyModifierItem,
    RankedMatchesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/applicant", tags=["applicant"])

# Maximum matches to return per section (configurable in Phase 9 policy editor)
_MAX_MATCHES = 100


# ---------------------------------------------------------------------------
# GET /applicant/me/profile
# ---------------------------------------------------------------------------

@router.get("/me/profile", response_model=ApplicantProfileSummary)
async def get_my_profile(
    current_user: Annotated[CurrentUser, Depends(require_applicant)],
) -> ApplicantProfileSummary:
    """
    Return the authenticated applicant's profile summary.
    Used by the dashboard header and profile-completeness indicator.
    """
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                a.id, a.first_name, a.last_name, a.program_name_raw,
                a.city, a.state, a.region,
                a.willing_to_relocate, a.willing_to_travel,
                a.expected_completion_date::text,
                a.available_from_date::text,
                jf.code AS canonical_job_family_code
            FROM public.applicants a
            LEFT JOIN public.canonical_job_families jf
                ON jf.id = a.canonical_job_family_id
            WHERE a.user_id = $1
            """,
            current_user.user_id,
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Applicant profile not found. Contact admin to link your account.",
        )

    completeness = _compute_completeness(dict(row))

    return ApplicantProfileSummary(
        applicant_id=str(row["id"]),
        first_name=row["first_name"],
        last_name=row["last_name"],
        program_name_raw=row["program_name_raw"],
        canonical_job_family_code=row["canonical_job_family_code"],
        city=row["city"],
        state=row["state"],
        region=row["region"],
        willing_to_relocate=bool(row["willing_to_relocate"]),
        willing_to_travel=bool(row["willing_to_travel"]),
        expected_completion_date=row["expected_completion_date"],
        available_from_date=row["available_from_date"],
        profile_completeness=completeness,
    )


# ---------------------------------------------------------------------------
# GET /applicant/me/matches
# ---------------------------------------------------------------------------

@router.get("/me/matches", response_model=RankedMatchesResponse)
async def get_my_matches(
    current_user: Annotated[CurrentUser, Depends(require_applicant)],
) -> RankedMatchesResponse:
    """
    Return ranked jobs for the authenticated applicant.

    Returns two sections (per SCORING_CONFIG.yaml §ui_visibility):
      eligible_matches  — "Best immediate opportunities"
      near_fit_matches  — "Promising near-fit opportunities"

    Ineligible matches are hidden.
    Both sections ordered by policy_adjusted_score DESC.
    """
    async with get_db() as conn:
        # Resolve user_id → applicant row
        app_row = await conn.fetchrow(
            """
            SELECT a.id, a.state AS app_state, a.region AS app_region,
                   a.canonical_job_family_id
            FROM public.applicants a
            WHERE a.user_id = $1
            """,
            current_user.user_id,
        )

        if not app_row:
            return RankedMatchesResponse(
                applicant_id="",
                eligible_matches=[],
                total_eligible=0,
                near_fit_matches=[],
                total_near_fit=0,
                has_matches=False,
                profile_has_family=False,
                profile_has_location=False,
            )

        applicant_id = str(app_row["id"])

        rows = await conn.fetch(
            """
            SELECT
                m.id          AS match_id,
                m.job_id::text,
                m.eligibility_status::text,
                m.match_label::text,
                m.policy_adjusted_score,
                m.top_strengths,
                m.top_gaps,
                m.required_missing_items,
                m.recommended_next_step,
                m.confidence_level::text,
                m.requires_review,
                j.title_normalized,
                j.title_raw,
                j.city         AS job_city,
                j.state        AS job_state,
                j.region       AS job_region,
                j.work_setting::text,
                j.travel_requirement,
                j.pay_min,
                j.pay_max,
                j.pay_type::text,
                e.name         AS employer_name,
                e.is_partner   AS is_partner_employer,
                $2::text       AS app_state,
                $3::text       AS app_region
            FROM public.matches m
            JOIN public.applicants a ON a.id = m.applicant_id
            JOIN public.jobs j        ON j.id = m.job_id
            JOIN public.employers e   ON e.id = j.employer_id
            WHERE a.user_id = $1
              AND m.is_visible_to_applicant = TRUE
              AND m.eligibility_status IN ('eligible', 'near_fit')
            ORDER BY m.policy_adjusted_score DESC NULLS LAST
            LIMIT $4
            """,
            current_user.user_id,
            app_row["app_state"],
            app_row["app_region"],
            _MAX_MATCHES,
        )

    eligible: list[JobMatchSummary] = []
    near_fit: list[JobMatchSummary] = []

    for row in rows:
        match = _row_to_summary(dict(row))
        if row["eligibility_status"] == "eligible":
            eligible.append(match)
        else:
            near_fit.append(match)

    return RankedMatchesResponse(
        applicant_id=applicant_id,
        eligible_matches=eligible,
        total_eligible=len(eligible),
        near_fit_matches=near_fit,
        total_near_fit=len(near_fit),
        has_matches=bool(eligible or near_fit),
        profile_has_family=bool(app_row["canonical_job_family_id"]),
        profile_has_location=bool(app_row["app_state"]),
    )


# ---------------------------------------------------------------------------
# GET /applicant/me/matches/{match_id}
# ---------------------------------------------------------------------------

@router.get("/me/matches/{match_id}", response_model=JobMatchDetail)
async def get_match_detail(
    match_id: str,
    current_user: Annotated[CurrentUser, Depends(require_applicant)],
) -> JobMatchDetail:
    """
    Return full match detail for one applicant-job pair.
    Includes dimension scores, gate rationale, and policy modifiers.
    The authenticated applicant may only view their own matches.
    """
    async with get_db() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                m.id          AS match_id,
                m.job_id::text,
                m.eligibility_status::text,
                m.match_label::text,
                m.policy_adjusted_score,
                m.base_fit_score,
                m.weighted_structured_score,
                m.semantic_score,
                m.top_strengths,
                m.top_gaps,
                m.required_missing_items,
                m.recommended_next_step,
                m.confidence_level::text,
                m.requires_review,
                m.hard_gate_rationale,
                m.policy_modifiers,
                j.title_normalized,
                j.title_raw,
                j.city         AS job_city,
                j.state        AS job_state,
                j.region       AS job_region,
                j.work_setting::text,
                j.travel_requirement,
                j.pay_min,
                j.pay_max,
                j.pay_type::text,
                e.name         AS employer_name,
                e.is_partner   AS is_partner_employer,
                a.state        AS app_state,
                a.region       AS app_region
            FROM public.matches m
            JOIN public.applicants a ON a.id = m.applicant_id
            JOIN public.jobs j        ON j.id = m.job_id
            JOIN public.employers e   ON e.id = j.employer_id
            WHERE m.id = $1::uuid
              AND a.user_id = $2
              AND m.is_visible_to_applicant = TRUE
            """,
            match_id,
            current_user.user_id,
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Match not found",
            )

        dim_rows = await conn.fetch(
            """
            SELECT dimension, weight, raw_score, weighted_score,
                   rationale, null_handling_applied, null_handling_default
            FROM public.match_dimension_scores
            WHERE match_id = $1::uuid
            ORDER BY weighted_score DESC
            """,
            match_id,
        )

    row_dict = dict(row)

    summary = _row_to_summary(row_dict)

    # Gate rationale: convert dict → list of GateResultItem
    gate_rationale_raw = row_dict.get("hard_gate_rationale") or {}
    gate_results = [
        GateResultItem(
            gate_name=gate,
            result=detail.get("result", ""),
            reason=detail.get("reason", ""),
            severity=detail.get("severity"),
        )
        for gate, detail in gate_rationale_raw.items()
    ]

    # Policy modifiers
    policy_mods_raw = row_dict.get("policy_modifiers") or []
    policy_mods = [
        PolicyModifierItem(
            policy=m.get("policy", ""),
            value=float(m.get("value", 0)),
            reason=m.get("reason", ""),
        )
        for m in policy_mods_raw
    ]

    # Dimension scores
    dimensions = [
        DimensionScoreItem(
            dimension=d["dimension"],
            weight=float(d["weight"]),
            raw_score=float(d["raw_score"]),
            weighted_score=float(d["weighted_score"]),
            rationale=d["rationale"],
            null_handling_applied=bool(d["null_handling_applied"]),
            null_handling_default=float(d["null_handling_default"]) if d["null_handling_default"] is not None else None,
        )
        for d in dim_rows
    ]

    required_missing = _safe_list(row_dict.get("required_missing_items"))

    return JobMatchDetail(
        **summary.model_dump(),
        base_fit_score=_safe_float(row_dict.get("base_fit_score")),
        weighted_structured_score=_safe_float(row_dict.get("weighted_structured_score")),
        semantic_score=_safe_float(row_dict.get("semantic_score")),
        required_missing_items=required_missing,
        hard_gate_rationale=gate_results,
        policy_modifiers=policy_mods,
        dimension_scores=dimensions,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _row_to_summary(row: dict[str, Any]) -> JobMatchSummary:
    """Convert a DB row dict to a JobMatchSummary."""
    return JobMatchSummary(
        match_id=str(row["match_id"]),
        job_id=str(row["job_id"]),
        job_title=row.get("title_normalized") or row.get("title_raw") or "Untitled",
        employer_name=row.get("employer_name") or "Unknown",
        is_partner_employer=bool(row.get("is_partner_employer", False)),
        job_city=row.get("job_city"),
        job_state=row.get("job_state"),
        job_region=row.get("job_region"),
        work_setting=row.get("work_setting"),
        travel_requirement=row.get("travel_requirement"),
        geography_note=_derive_geography_note(row),
        pay_min=_safe_float(row.get("pay_min")),
        pay_max=_safe_float(row.get("pay_max")),
        pay_type=row.get("pay_type"),
        eligibility_status=row.get("eligibility_status", "near_fit"),
        match_label=row.get("match_label"),
        policy_adjusted_score=_safe_float(row.get("policy_adjusted_score")),
        top_strengths=_safe_list(row.get("top_strengths")),
        top_gaps=_safe_list(row.get("top_gaps")),
        recommended_next_step=row.get("recommended_next_step"),
        confidence_level=row.get("confidence_level"),
        requires_review=bool(row.get("requires_review", False)),
    )


def _derive_geography_note(row: dict[str, Any]) -> str | None:
    """Derive a human-readable geography note for the applicant."""
    ws = (row.get("work_setting") or "").lower()
    if ws == "remote":
        return "Remote — open to all locations"

    job_state = row.get("job_state")
    job_city = row.get("job_city")
    app_state = row.get("app_state")
    app_region = row.get("app_region")
    job_region = row.get("job_region")

    if not job_state:
        return None

    if app_state and app_state.upper() == job_state.upper():
        return f"Same state as you ({job_state})"

    if app_region and job_region and app_region == job_region:
        return f"Same region ({job_region})"

    location_str = " ".join(filter(None, [job_city, job_state])).strip()
    return f"Location: {location_str}" if location_str else None


def _compute_completeness(row: dict[str, Any]) -> int:
    """Rough profile completeness score (0–100)."""
    score = 0
    if row.get("program_name_raw") or row.get("canonical_job_family_code"):
        score += 25
    if row.get("state"):
        score += 20
    if row.get("expected_completion_date") or row.get("available_from_date"):
        score += 20
    if row.get("city"):
        score += 10
    # willing_to_relocate / willing_to_travel are booleans — always "set"
    score += 15
    if row.get("program_name_raw") and len(row["program_name_raw"]) > 10:
        score += 10
    return min(score, 100)


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(v) for v in val]
    return []
