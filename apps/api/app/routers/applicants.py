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
                a.enrollment_status::text, a.degree_type::text,
                a.school_name, a.school_city, a.school_state,
                a.career_path, a.program_field, a.specific_career,
                a.program_start_date::text, a.gpa,
                a.travel_preference::text, a.relocation_preference::text,
                a.relocation_states,
                a.age_range, a.gender, a.military_status, a.military_dependent,
                a.current_wages, a.has_internship, a.activities,
                a.honor_societies,
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
        enrollment_status=row["enrollment_status"],
        degree_type=row["degree_type"],
        school_name=row["school_name"],
        school_city=row["school_city"],
        school_state=row["school_state"],
        career_path=row["career_path"],
        program_field=row["program_field"],
        specific_career=row["specific_career"],
        program_start_date=row["program_start_date"],
        gpa=float(row["gpa"]) if row["gpa"] is not None else None,
        travel_preference=row["travel_preference"],
        relocation_preference=row["relocation_preference"],
        relocation_states=row["relocation_states"] or [],
        age_range=row["age_range"],
        gender=row["gender"],
        military_status=bool(row["military_status"]),
        military_dependent=bool(row["military_dependent"]),
        current_wages=row["current_wages"],
        has_internship=bool(row["has_internship"]),
        activities=row["activities"],
        honor_societies=row["honor_societies"] or [],
    )


# ---------------------------------------------------------------------------
# PATCH /applicant/me/profile  — onboarding / profile update
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _BaseModel

class ProfileUpdateRequest(_BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    program_name_raw: str | None = None
    city: str | None = None
    state: str | None = None
    willing_to_relocate: bool | None = None
    willing_to_travel: bool | None = None
    expected_completion_date: str | None = None
    available_from_date: str | None = None
    onboarding_complete: bool | None = None
    # Expanded fields
    enrollment_status: str | None = None
    degree_type: str | None = None
    school_name: str | None = None
    school_campus: str | None = None
    school_city: str | None = None
    school_state: str | None = None
    career_path: str | None = None
    program_field: str | None = None
    specific_career: str | None = None
    program_start_date: str | None = None
    gpa: float | None = None
    travel_preference: str | None = None
    relocation_preference: str | None = None
    relocation_states: list[str] | None = None
    age_range: str | None = None
    gender: str | None = None
    military_status: bool | None = None
    military_dependent: bool | None = None
    current_wages: str | None = None
    has_internship: bool | None = None
    internship_details: str | None = None
    essay_background: str | None = None
    essay_impact: str | None = None
    activities: str | None = None
    honor_societies: list[str] | None = None


@router.patch("/me/profile", status_code=status.HTTP_200_OK)
async def update_my_profile(
    body: ProfileUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(require_applicant)],
) -> dict:
    """
    Update the authenticated applicant's profile.
    Called during onboarding and from the profile edit page.
    Only non-None fields are updated (partial update).

    Side-effects:
      - Auto-normalizes program_name_raw → canonical_job_family_id
      - Auto-normalizes state → region
      - Syncs onboarding_complete to user_profiles table
    """
    updates: dict[str, Any] = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return {"updated": False}

    # Convert date strings to date objects for asyncpg
    from datetime import date as _date
    for date_field in ("expected_completion_date", "available_from_date", "program_start_date"):
        if date_field in updates and isinstance(updates[date_field], str):
            try:
                updates[date_field] = _date.fromisoformat(updates[date_field])
            except ValueError:
                updates.pop(date_field)

    async with get_db() as conn:
        # Auto-normalize program → canonical job family
        # Try multiple fields in priority order: program_field > specific_career > program_name_raw
        import uuid as _uuid
        program_name = (
            updates.get("program_field")
            or updates.get("specific_career")
            or updates.get("program_name_raw")
        )
        if program_name:
            family_id = await _resolve_job_family(conn, program_name)
            if family_id:
                updates["canonical_job_family_id"] = _uuid.UUID(family_id)

        # Auto-normalize state → region
        state_val = updates.get("state")
        if state_val:
            region = await _resolve_region(conn, state_val)
            if region:
                updates["region"] = region

        # Remove onboarding_complete from applicants update; handle separately
        onboarding_val = updates.pop("onboarding_complete", None)

        if updates:
            set_clauses = [f"{col} = ${i+2}" for i, col in enumerate(updates)]
            values = list(updates.values())

            row = await conn.fetchrow(
                f"""
                UPDATE public.applicants
                SET {", ".join(set_clauses)}, updated_at = NOW(), profile_last_updated_at = NOW()
                WHERE user_id = $1
                RETURNING id
                """,
                current_user.user_id,
                *values,
            )
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Applicant profile not found.",
                )

        # Sync onboarding_complete to BOTH tables
        if onboarding_val is not None:
            await conn.execute(
                "UPDATE public.applicants SET onboarding_complete = $2, updated_at = NOW() WHERE user_id = $1",
                current_user.user_id, onboarding_val,
            )
            await conn.execute(
                "UPDATE public.user_profiles SET onboarding_complete = $2, updated_at = NOW() WHERE user_id = $1",
                current_user.user_id, onboarding_val,
            )

    return {"updated": True, "auto_normalized": bool(program_name and updates.get("canonical_job_family_id"))}


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
                j.source_url,
                jf.code        AS canonical_job_family_code,
                j.description_raw,
                j.requirements_raw,
                j.preferred_qualifications_raw,
                j.experience_level,
                $2::text       AS app_state,
                $3::text       AS app_region
            FROM public.matches m
            JOIN public.applicants a ON a.id = m.applicant_id
            JOIN public.jobs j        ON j.id = m.job_id
            JOIN public.employers e   ON e.id = j.employer_id
            LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
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
                j.source_url,
                jf.code        AS canonical_job_family_code,
                j.description_raw,
                j.requirements_raw,
                j.preferred_qualifications_raw,
                j.experience_level,
                a.state        AS app_state,
                a.region       AS app_region
            FROM public.matches m
            JOIN public.applicants a ON a.id = m.applicant_id
            JOIN public.jobs j        ON j.id = m.job_id
            JOIN public.employers e   ON e.id = j.employer_id
            LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
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
        source_url=row.get("source_url"),
        canonical_job_family_code=row.get("canonical_job_family_code"),
        description_raw=row.get("description_raw"),
        requirements_raw=row.get("requirements_raw"),
        preferred_qualifications_raw=row.get("preferred_qualifications_raw"),
        experience_level=row.get("experience_level"),
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
    """Profile completeness score (0–100). Weighted by matching importance."""
    score = 0
    # Core identity (20)
    if row.get("first_name") and row.get("last_name"):
        score += 10
    if row.get("program_name_raw") or row.get("program_field"):
        score += 10
    # Job family normalization (15) — critical for matching
    if row.get("canonical_job_family_code"):
        score += 15
    # Location (15)
    if row.get("state"):
        score += 10
    if row.get("city"):
        score += 5
    # Availability (15)
    if row.get("expected_completion_date") or row.get("available_from_date"):
        score += 15
    # Education details (10)
    if row.get("school_name"):
        score += 5
    if row.get("enrollment_status") or row.get("degree_type"):
        score += 5
    # Travel/relocation preferences (10)
    if row.get("travel_preference") or row.get("willing_to_relocate") is not None:
        score += 5
    if row.get("relocation_preference") or row.get("willing_to_travel") is not None:
        score += 5
    # Experience signals (10)
    if row.get("has_internship"):
        score += 5
    if row.get("gpa"):
        score += 5
    # Demographics (5)
    if row.get("age_range") or row.get("gender"):
        score += 5
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


# ---------------------------------------------------------------------------
# Auto-normalization helpers (run on profile save)
# ---------------------------------------------------------------------------

import re as _re

async def _resolve_job_family(conn: Any, program_name: str) -> str | None:
    """
    Fuzzy-match program_name_raw against canonical_job_families.
    Returns the UUID of the best-matching family, or None.
    Uses the same strategy as packages/matching/normalizer.py but inline
    to avoid cross-package import issues.
    """
    rows = await conn.fetch(
        "SELECT id, code, name, aliases FROM public.canonical_job_families WHERE is_active = TRUE"
    )
    if not rows:
        return None

    name_lower = program_name.strip().lower()

    # 1. Exact match on code or name
    for r in rows:
        if name_lower == r["code"].lower() or name_lower == r["name"].lower():
            return str(r["id"])

    # 2. Alias substring match
    matches = []
    for r in rows:
        aliases = r["aliases"] or []
        for alias in aliases:
            al = alias.lower()
            if al in name_lower or name_lower in al:
                matches.append(r)
                break

    if len(matches) == 1:
        return str(matches[0]["id"])
    if len(matches) > 1:
        return str(matches[0]["id"])

    # 3. Keyword overlap
    best_id = None
    best_score = 0
    for r in rows:
        score = 0
        sources = [r["code"], r["name"]] + (r["aliases"] or [])
        for src in sources:
            for word in _re.split(r"[\s/,\-]+", src.lower()):
                if len(word) >= 4 and word in name_lower:
                    score += 1
        if score > best_score:
            best_score = score
            best_id = str(r["id"])

    if best_id and best_score >= 1:
        return best_id

    # 4. LLM fallback: ask an LLM to classify when deterministic matching fails
    return await _llm_resolve_job_family(program_name, rows)


async def _llm_resolve_job_family(program_name: str, families: list) -> str | None:
    """
    Last-resort LLM classification of program name → canonical job family.
    Returns the family UUID or None if the LLM call fails or is unavailable.
    """
    import os
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    family_list = "\n".join(
        f"- {r['code']}: {r['name']} (aliases: {', '.join(r['aliases'] or [])})"
        for r in families
    )
    prompt = (
        f"Given this list of canonical skilled-trades job families:\n{family_list}\n\n"
        f"Which SINGLE job family code best matches this applicant program: \"{program_name}\"?\n"
        f"Respond with ONLY the code (e.g. 'electrical') or 'none' if no match."
    )

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 30,
                },
            )
        if resp.status_code != 200:
            return None
        answer = resp.json()["choices"][0]["message"]["content"].strip().lower()
        if answer == "none" or not answer:
            return None
        for r in families:
            if r["code"].lower() == answer:
                return str(r["id"])
        return None
    except Exception:
        return None


async def _resolve_region(conn: Any, state: str) -> str | None:
    """Map a US state code to a region code using geography_regions."""
    rows = await conn.fetch(
        "SELECT code, states FROM public.geography_regions WHERE is_active = TRUE"
    )
    state_upper = state.strip().upper()
    for r in rows:
        states = r["states"] or []
        if state_upper in [s.upper() for s in states]:
            return r["code"]
    return None
