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

import asyncio as _asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

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


def _parse_required_creds(raw: str | None) -> list[dict]:
    """jobs.required_credentials_canonical jsonb -> chip-ready list."""
    if not raw:
        return []
    import json as _json
    try:
        items = _json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [
        {"name": i.get("name"), "requirement": i.get("requirement", "mentioned")}
        for i in items
        if isinstance(i, dict) and i.get("name")
    ]

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
                a.id, a.first_name, a.last_name, a.phone, a.program_name_raw,
                a.city, a.state, a.region, a.lat, a.lng,
                a.willing_to_relocate, a.willing_to_travel,
                a.commute_radius_miles,
                a.expected_completion_date::text,
                a.available_from_date::text,
                a.enrollment_status::text, a.degree_type::text,
                a.school_name, a.school_city, a.school_state,
                a.career_path, a.program_field, a.specific_career,
                a.sector_code,
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
            WHERE a.id = COALESCE($2::uuid, (SELECT id FROM public.applicants WHERE user_id = $1::uuid))
            """,
            current_user.user_id,
            current_user.view_as_applicant_id,
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
        phone=row.get("phone"),
        program_name_raw=row["program_name_raw"],
        canonical_job_family_code=row["canonical_job_family_code"],
        sector_code=row.get("sector_code"),
        city=row["city"],
        state=row["state"],
        region=row["region"],
        # .get(): works on asyncpg.Record AND the plain-dict rows test mocks use.
        lat=float(row.get("lat")) if row.get("lat") is not None else None,
        lng=float(row.get("lng")) if row.get("lng") is not None else None,
        willing_to_relocate=bool(row["willing_to_relocate"]),
        willing_to_travel=bool(row["willing_to_travel"]),
        commute_radius_miles=row["commute_radius_miles"],
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
from pydantic import Field as _Field
from pydantic import field_validator as _field_validator


class ProfileUpdateRequest(_BaseModel):
    first_name: str | None = _Field(default=None, max_length=120)
    last_name: str | None = _Field(default=None, max_length=120)
    # Same shape/limit as the apply sheet's inline profile completion — this
    # is the number SMS notifications use.
    phone: str | None = _Field(default=None, max_length=40)
    program_name_raw: str | None = _Field(default=None, max_length=200)
    city: str | None = _Field(default=None, max_length=120)
    state: str | None = _Field(default=None, max_length=50)
    willing_to_relocate: bool | None = None
    willing_to_travel: bool | None = None
    # Commute radius in miles around the home city — drives geography gating.
    commute_radius_miles: int | None = _Field(default=None, ge=1, le=500)
    expected_completion_date: str | None = None
    available_from_date: str | None = None
    onboarding_complete: bool | None = None
    # Expanded fields
    enrollment_status: str | None = _Field(default=None, max_length=120)
    degree_type: str | None = _Field(default=None, max_length=120)
    school_name: str | None = _Field(default=None, max_length=200)
    school_campus: str | None = _Field(default=None, max_length=200)
    school_city: str | None = _Field(default=None, max_length=120)
    school_state: str | None = _Field(default=None, max_length=50)
    career_path: str | None = _Field(default=None, max_length=200)
    program_field: str | None = _Field(default=None, max_length=200)
    specific_career: str | None = _Field(default=None, max_length=200)
    # SKILLED Nation taxonomy: sector + career field codes. Validated as a
    # pair against the generated taxonomy (422 on mismatch) and enforced
    # again by a DB trigger.
    sector_code: str | None = _Field(default=None, max_length=40)
    field_code: str | None = _Field(default=None, max_length=80)
    program_start_date: str | None = None
    gpa: float | None = _Field(default=None, ge=0, le=5)
    travel_preference: str | None = _Field(default=None, max_length=120)
    relocation_preference: str | None = _Field(default=None, max_length=120)
    relocation_states: list[str] | None = _Field(default=None, max_length=60)
    age_range: str | None = _Field(default=None, max_length=50)
    gender: str | None = _Field(default=None, max_length=50)
    military_status: bool | None = None
    military_dependent: bool | None = None
    current_wages: str | None = _Field(default=None, max_length=120)
    has_internship: bool | None = None
    internship_details: str | None = _Field(default=None, max_length=5000)
    essay_background: str | None = _Field(default=None, max_length=10000)
    essay_impact: str | None = _Field(default=None, max_length=10000)
    activities: str | None = _Field(default=None, max_length=5000)
    honor_societies: list[str] | None = _Field(default=None, max_length=50)

    @_field_validator(
        "expected_completion_date", "available_from_date", "program_start_date"
    )
    @classmethod
    def _valid_iso_date(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        from datetime import date as _date
        try:
            _date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError("must be an ISO date (YYYY-MM-DD)") from exc
        return v

    @_field_validator("relocation_states", "honor_societies")
    @classmethod
    def _short_list_items(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        for item in v:
            if len(item) > 120:
                raise ValueError("list items must be 120 characters or fewer")
        return v


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

    # Taxonomy pair validation happens BEFORE any write: an invalid
    # sector/field combination is a 422, never a half-applied update.
    from app.util.taxonomy_api import (
        default_sector_for_field,
        resolve_family_uuid,
        validate_sector_field,
    )
    field_code = updates.pop("field_code", None)
    sector_code = updates.get("sector_code")
    validate_sector_field(sector_code, field_code)
    if field_code and not sector_code:
        implied = default_sector_for_field(field_code)
        if implied:
            updates["sector_code"] = implied

    async with get_db() as conn:
        import uuid as _uuid
        # Referenced by the auto_normalized response flag regardless of path.
        program_name = (
            updates.get("program_field")
            or updates.get("specific_career")
            or updates.get("program_name_raw")
        )
        if field_code:
            fam = await resolve_family_uuid(conn, field_code)
            if fam is None:
                raise HTTPException(status_code=422, detail=f"Unknown career field '{field_code}'.")
            updates["canonical_job_family_id"] = fam
        elif program_name:
            # Legacy path: fuzzy-normalize free text when no explicit field
            # was chosen. Priority: program_field > specific_career > raw.
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

        # Instrument "profile completed" — emitted once per applicant, the
        # first time profile_completeness crosses 80 after a profile write.
        # (The snapshot also feeds the home geocode below.)
        fresh = await conn.fetchrow(
            """
            SELECT a.id, a.first_name, a.last_name, a.program_name_raw, a.program_field,
                   a.city, a.state, a.zip_code, a.lat,
                   a.expected_completion_date, a.available_from_date,
                   a.school_name, a.enrollment_status::text, a.degree_type::text,
                   a.travel_preference::text, a.relocation_preference::text,
                   a.willing_to_relocate, a.willing_to_travel,
                   a.has_internship, a.gpa, a.age_range, a.gender,
                   jf.code AS canonical_job_family_code
            FROM public.applicants a
            LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
            WHERE a.user_id = $1
            """,
            current_user.user_id,
        )
        if fresh is not None:
            completeness = _compute_completeness(dict(fresh))
            if completeness >= 80:
                await conn.execute(
                    """
                    INSERT INTO public.engagement_events (applicant_id, event_type, event_data)
                    SELECT $1, 'profile_completed', $2::jsonb
                    WHERE NOT EXISTS (
                        SELECT 1 FROM public.engagement_events ee
                        WHERE ee.applicant_id = $1 AND ee.event_type = 'profile_completed'
                    )
                    """,
                    fresh["id"],
                    {"profile_completeness": completeness},
                )

        # Geography is first-class: resolve home coordinates whenever location
        # changed (or was never resolved) so the matching engine can apply the
        # commute-radius rule with pre-resolved coords. Cached in geocode_cache;
        # a Nominatim miss/timeout degrades gracefully to state-level gating.
        if fresh is not None and (
            updates.keys() & {"city", "state"} or "commute_radius_miles" in updates
        ):
            try:
                snap = dict(fresh)
                needs_geocode = (
                    updates.keys() & {"city", "state"} or snap.get("lat") is None
                )
                if needs_geocode and (snap.get("city") or snap.get("state")):
                    from app.skilled_pro.geocode import geocode
                    coords = await geocode(
                        conn,
                        city=snap.get("city") or "",
                        state=snap.get("state") or "",
                        zip_code=snap.get("zip_code") or "",
                    )
                    if coords:
                        await conn.execute(
                            "UPDATE public.applicants SET lat = $2, lng = $3 WHERE user_id = $1",
                            current_user.user_id, coords[0], coords[1],
                        )
            except Exception:
                logger.warning("Home geocode failed on profile save", exc_info=True)

    # Fire-and-forget: recompute matches if significant fields changed
    significant = {"program_name_raw", "program_field", "specific_career", "state",
                   "willing_to_relocate", "canonical_job_family_id",
                   # Geography inputs — a radius or location change must be
                   # reflected in this applicant's matches without waiting
                   # for the 6-hour batch.
                   "commute_radius_miles", "city", "relocation_states",
                   "relocation_preference", "travel_preference"}
    if updates.keys() & significant:
        import asyncio as _asyncio

        from app.worker.scheduler import trigger_recompute_for_applicant
        # The snapshot above already carries this applicant's UUID.
        _app_id = str(fresh["id"]) if fresh is not None else None
        if _app_id:
            _asyncio.create_task(trigger_recompute_for_applicant(_app_id))

    return {"updated": True, "auto_normalized": bool(program_name and updates.get("canonical_job_family_id"))}


# ---------------------------------------------------------------------------
# GET /applicant/me/matches
# ---------------------------------------------------------------------------

@router.get("/me/matches", response_model=RankedMatchesResponse)
async def get_my_matches(
    current_user: Annotated[CurrentUser, Depends(require_applicant)],
    eligible_offset: Annotated[int, Query(ge=0)] = 0,
    near_fit_offset: Annotated[int, Query(ge=0)] = 0,
    nearby_offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=_MAX_MATCHES)] = _MAX_MATCHES,
) -> RankedMatchesResponse:
    """
    Return ranked jobs for the authenticated applicant.

    Returns two sections (per SCORING_CONFIG.yaml §ui_visibility):
      eligible_matches  — "Best immediate opportunities"
      near_fit_matches  — "Promising near-fit opportunities"

    Ineligible matches are hidden.
    Both sections ordered by policy_adjusted_score DESC.

    Additive pagination (per tier): `eligible_offset` / `near_fit_offset` /
    `nearby_offset` skip past already-served rows in that tier; `limit` caps
    each tier's page. Defaults (0/0/0, limit=100) keep the original
    "top slice of every tier" behavior, and total_* counts are always the
    TRUE totals regardless of paging.
    """
    async with get_db() as conn:
        # Resolve caller → applicant row (view-as resolves by applicant id
        # directly so bulk-imported applicants with no auth user still work)
        app_row = await conn.fetchrow(
            """
            SELECT a.id, a.state AS app_state, a.region AS app_region,
                   a.canonical_job_family_id
            FROM public.applicants a
            WHERE a.id = COALESCE($2::uuid, (SELECT id FROM public.applicants WHERE user_id = $1::uuid))
            """,
            current_user.user_id,
            current_user.view_as_applicant_id,
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

        # True totals, independent of the display LIMIT below. Predicates must
        # stay identical to the list query (visibility + eligibility) so the
        # headline counts ("ready to apply to N jobs") never drift from what
        # actually exists — len() of a LIMITed list undercounts past _MAX_MATCHES.
        # Relaxation floor from the ACTIVE policy config (fallback: defaults).
        # Controls when the geography-only "nearby" tier unlocks — sparse
        # applicants see labeled nearby jobs instead of a blank page.
        relax_raw = await conn.fetchval(
            "SELECT config->'relaxation' FROM public.policy_configs WHERE is_active = TRUE LIMIT 1"
        )
        relax_enabled, relax_floor, tier_nearby_on = True, 5, True
        if relax_raw:
            import json as _json
            relax_cfg = relax_raw if isinstance(relax_raw, dict) else _json.loads(relax_raw)
            relax_enabled = bool(relax_cfg.get("enabled", True))
            relax_floor = int(relax_cfg.get("min_results", 5))
            tier_nearby_on = bool((relax_cfg.get("tiers") or {}).get("nearby_other_trade", True))

        count_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE m.eligibility_status = 'eligible') AS n_eligible,
                COUNT(*) FILTER (WHERE m.eligibility_status = 'near_fit') AS n_near_fit,
                COUNT(*) FILTER (WHERE m.match_tier = 'nearby')           AS n_nearby
            FROM public.matches m
            JOIN public.applicants a ON a.id = m.applicant_id
            WHERE a.id = $1
              AND m.is_visible_to_applicant = TRUE
              AND (m.eligibility_status IN ('eligible', 'near_fit')
                   OR m.match_tier = 'nearby')
            """,
            app_row["id"],
        )
        total_eligible = int(count_row["n_eligible"] or 0)
        total_near_fit = int(count_row["n_near_fit"] or 0)
        total_nearby = int(count_row["n_nearby"] or 0)

        # Nearby tier unlocks only when the stricter sections are thin.
        include_nearby = (
            relax_enabled and tier_nearby_on
            and (total_eligible + total_near_fit) < relax_floor
            and total_nearby > 0
        )

        # Per-tier list queries so each tier pages independently (additive
        # offset/limit params). Tier predicates mirror the count query's
        # bucketing exactly: nearby tier is its own shelf, never double-served
        # inside eligible/near_fit.
        _select_cols = """
            SELECT
                m.id          AS match_id,
                m.job_id::text,
                m.eligibility_status::text,
                m.match_label::text,
                m.policy_adjusted_score,
                m.match_tier,
                m.tier_reason,
                m.distance_miles,
                m.top_strengths,
                m.top_gaps,
                m.required_missing_items,
                m.recommended_next_step,
                m.confidence_level::text,
                m.score_evidence_pct,
                m.requires_review,
                m.score_evidence_pct,
                m.n_gaps,
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
                COALESCE(j.accepts_internal_applications,
                         e.accepts_internal_applications_default,
                         FALSE) AS internal_apply,
                j.description_raw,
                j.requirements_raw,
                j.preferred_qualifications_raw,
                j.experience_level,
                j.required_credentials_canonical::text AS req_creds_json,
                $2::text       AS app_state,
                $3::text       AS app_region,
                sj.interest_level AS applicant_interest
            FROM public.matches m
            JOIN public.applicants a ON a.id = m.applicant_id
            JOIN public.jobs j        ON j.id = m.job_id
            JOIN public.employers e   ON e.id = j.employer_id
            LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
            LEFT JOIN public.saved_jobs sj ON sj.applicant_id = a.id AND sj.job_id = m.job_id
            WHERE a.id = $1
              AND m.is_visible_to_applicant = TRUE
        """
        # Gap count outranks score: a one-gap near-fit is a better lead than
        # a three-gap one whatever their (tightly clustered) scores say.
        # Eligible rows all have n_gaps=0, so their order is unchanged.
        _score_order = """
            ORDER BY m.n_gaps ASC NULLS LAST,
                     m.policy_adjusted_score DESC NULLS LAST,
                     m.distance_miles ASC NULLS LAST,
                     m.job_id
            LIMIT $4 OFFSET $5
        """

        async def _fetch_tier(predicate: str, order: str, offset: int):
            return await conn.fetch(
                _select_cols + predicate + order,
                app_row["id"],
                app_row["app_state"],
                app_row["app_region"],
                limit,
                offset,
            )

        eligible_rows = await _fetch_tier(
            " AND m.eligibility_status = 'eligible' AND m.match_tier IS DISTINCT FROM 'nearby' ",
            _score_order,
            eligible_offset,
        )
        near_fit_rows = await _fetch_tier(
            " AND m.eligibility_status = 'near_fit' AND m.match_tier IS DISTINCT FROM 'nearby' ",
            _score_order,
            near_fit_offset,
        )
        nearby_rows = []
        if include_nearby:
            # Nearby is an honest fallback shelf — ordered by distance first
            # (its whole premise is "because you're nearby"), never blended
            # into the score order. Ordering in SQL keeps pagination stable.
            nearby_rows = await _fetch_tier(
                " AND m.match_tier = 'nearby' ",
                """
                ORDER BY m.distance_miles ASC NULLS LAST,
                         m.policy_adjusted_score DESC NULLS LAST,
                         m.job_id
                LIMIT $4 OFFSET $5
                """,
                nearby_offset,
            )

    eligible = [_row_to_summary(dict(r)) for r in eligible_rows]
    near_fit = [_row_to_summary(dict(r)) for r in near_fit_rows]
    nearby = [_row_to_summary(dict(r)) for r in nearby_rows]

    # Ranked-impression log (fire-and-forget): what was shown, where, with the
    # scoring state used at serve time. Joined with engagement_events this is
    # the ground truth for offline evaluation and any future learned ranker —
    # click data without serve-time positions is unusable (position bias).
    _asyncio.create_task(_log_impressions(
        applicant_id,
        [("eligible", eligible_offset, eligible_rows),
         ("near_fit", near_fit_offset, near_fit_rows),
         ("nearby", nearby_offset, nearby_rows)],
    ))

    return RankedMatchesResponse(
        applicant_id=applicant_id,
        eligible_matches=eligible,
        total_eligible=total_eligible,
        near_fit_matches=near_fit,
        total_near_fit=total_near_fit,
        nearby_matches=nearby,
        total_nearby=total_nearby if include_nearby else 0,
        relaxation_applied=include_nearby,
        # True totals, not the served page — an offset past the end of a tier
        # must not flip the page into the "no matches" empty state.
        has_matches=bool(total_eligible or total_near_fit or (include_nearby and total_nearby)),
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
                m.match_tier,
                m.tier_reason,
                m.distance_miles,
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
                COALESCE(j.accepts_internal_applications,
                         e.accepts_internal_applications_default,
                         FALSE) AS internal_apply,
                j.description_raw,
                j.requirements_raw,
                j.preferred_qualifications_raw,
                j.experience_level,
                j.required_credentials_canonical::text AS req_creds_json,
                a.state        AS app_state,
                a.region       AS app_region
            FROM public.matches m
            JOIN public.applicants a ON a.id = m.applicant_id
            JOIN public.jobs j        ON j.id = m.job_id
            JOIN public.employers e   ON e.id = j.employer_id
            LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
            WHERE m.id = $1::uuid
              AND a.id = COALESCE($3::uuid, (SELECT id FROM public.applicants WHERE user_id = $2::uuid))
              AND m.is_visible_to_applicant = TRUE
            """,
            match_id,
            current_user.user_id,
            current_user.view_as_applicant_id,
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Match not found",
            )

        # Instrument the funnel's "viewed a match" step — server-side at the
        # moment of truth, deduped to one event per applicant/match/day so
        # refreshes don't inflate counts. (Admin engagement funnels read this.)
        # Suppressed under admin view-as: debug views must not pollute the
        # applicant's engagement funnel.
        if not current_user.is_view_as:
            await conn.execute(
                """
                INSERT INTO public.engagement_events (applicant_id, match_id, job_id, event_type, event_data)
                SELECT m.applicant_id, m.id, m.job_id, 'match_view', '{}'::jsonb
                FROM public.matches m
                WHERE m.id = $1::uuid
                  AND NOT EXISTS (
                    SELECT 1 FROM public.engagement_events ee
                    WHERE ee.match_id = $1::uuid AND ee.event_type = 'match_view'
                      AND ee.created_at >= date_trunc('day', now())
                  )
                """,
                match_id,
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

async def _log_impressions(
    applicant_id: str,
    tiers: list[tuple[str, int, list[Any]]],
) -> None:
    """Batch-insert the served ranked rows into match_impressions.

    Best-effort: an analytics write must never fail a page load, so every
    error is swallowed into a log line.
    """
    try:
        values = []
        for tier, offset, rows in tiers:
            for i, r in enumerate(rows):
                row = dict(r)
                values.append((
                    applicant_id, str(row["job_id"]), str(row["match_id"]),
                    "applicant_matches", offset + i + 1, tier,
                    row.get("policy_adjusted_score"), row.get("n_gaps"),
                    row.get("score_evidence_pct"),
                ))
        if not values:
            return
        async with get_db() as conn:
            await conn.executemany(
                """INSERT INTO public.match_impressions
                       (applicant_id, job_id, match_id, context, position,
                        tier, score, n_gaps, evidence_pct)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                values,
            )
    except Exception:  # noqa: BLE001 - analytics must never break serving
        logger.warning("match_impressions insert failed", exc_info=True)


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
        internal_apply=bool(row.get("internal_apply", False)),
        description_raw=row.get("description_raw"),
        requirements_raw=row.get("requirements_raw"),
        required_credentials=_parse_required_creds(row.get("req_creds_json")),
        preferred_qualifications_raw=row.get("preferred_qualifications_raw"),
        experience_level=row.get("experience_level"),
        confidence_level=row.get("confidence_level"),
        score_evidence_pct=_safe_float(row.get("score_evidence_pct")),
        n_gaps=row.get("n_gaps"),
        requires_review=bool(row.get("requires_review", False)),
        applicant_interest=row.get("applicant_interest"),
        match_tier=row.get("match_tier"),
        tier_reason=row.get("tier_reason"),
        distance_miles=_safe_float(row.get("distance_miles")),
    )


def _derive_geography_note(row: dict[str, Any]) -> str | None:
    """Derive a human-readable geography note for the applicant."""
    ws = (row.get("work_setting") or "").lower()
    if ws == "remote":
        return "Remote, open to all locations"

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
# GET /applicant/me/matches/{match_id}/interest
# POST /applicant/me/matches/{match_id}/interest
# ---------------------------------------------------------------------------

class InterestSignalRequest(_BaseModel):
    # 'interested' | 'applied' | 'not_interested' — or null to clear the signal
    interest_level: str | None = None


class InterestSignalResponse(_BaseModel):
    match_id: str
    job_id: str
    interest_level: str | None
    updated_at: str | None


@router.get("/me/matches/{match_id}/interest", response_model=InterestSignalResponse)
async def get_interest_signal(
    match_id: str,
    current_user: Annotated[CurrentUser, Depends(require_applicant)],
) -> InterestSignalResponse:
    """Return the applicant's current interest signal for this match."""
    async with get_db() as conn:
        # Verify match ownership
        match_row = await conn.fetchrow(
            """
            SELECT m.id::text AS match_id, m.job_id::text
            FROM public.matches m
            JOIN public.applicants a ON a.id = m.applicant_id
            WHERE m.id = $1::uuid
              AND a.id = COALESCE($3::uuid, (SELECT id FROM public.applicants WHERE user_id = $2::uuid))
            """,
            match_id, current_user.user_id, current_user.view_as_applicant_id,
        )
        if not match_row:
            raise HTTPException(status_code=404, detail="Match not found")

        signal_row = await conn.fetchrow(
            """
            SELECT interest_level, updated_at::text
            FROM public.saved_jobs sj
            JOIN public.applicants a ON a.id = sj.applicant_id
            WHERE sj.job_id = $1::uuid
              AND a.id = COALESCE($3::uuid, (SELECT id FROM public.applicants WHERE user_id = $2::uuid))
            """,
            match_row["job_id"], current_user.user_id, current_user.view_as_applicant_id,
        )

    return InterestSignalResponse(
        match_id=match_row["match_id"],
        job_id=match_row["job_id"],
        interest_level=signal_row["interest_level"] if signal_row else None,
        updated_at=signal_row["updated_at"] if signal_row else None,
    )


@router.post("/me/matches/{match_id}/interest", response_model=InterestSignalResponse)
async def set_interest_signal(
    match_id: str,
    body: InterestSignalRequest,
    current_user: Annotated[CurrentUser, Depends(require_applicant)],
) -> InterestSignalResponse:
    """
    Set, update, or clear the applicant's interest signal for a matched job.
    Non-null level upserts into saved_jobs; null deletes the row (clear).
    Logs an engagement event only when the state actually changed.
    """
    valid_levels = {"interested", "applied", "not_interested"}
    if body.interest_level is not None and body.interest_level not in valid_levels:
        raise HTTPException(
            status_code=422,
            detail=f"interest_level must be null or one of: {', '.join(sorted(valid_levels))}",
        )

    async with get_db() as conn:
        # Get applicant_id + job_id from match
        row = await conn.fetchrow(
            """
            SELECT m.job_id::text, a.id AS applicant_id
            FROM public.matches m
            JOIN public.applicants a ON a.id = m.applicant_id
            WHERE m.id = $1::uuid AND a.user_id = $2
              AND m.is_visible_to_applicant = TRUE
            """,
            match_id, current_user.user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Match not found")

        job_id = row["job_id"]
        applicant_id = row["applicant_id"]

        # Capture the previous level so events fire only on ACTUAL state change —
        # re-clicking the already-active pill must not mint another event
        # (analytics counts raw events; repeats inflated the funnel before).
        prev_level = await conn.fetchval(
            "SELECT interest_level FROM public.saved_jobs WHERE applicant_id = $1 AND job_id = $2::uuid",
            applicant_id, job_id,
        )

        if body.interest_level is None:
            # Clear: delete the saved_jobs row entirely.
            await conn.execute(
                "DELETE FROM public.saved_jobs WHERE applicant_id = $1 AND job_id = $2::uuid",
                applicant_id, job_id,
            )
            signal_row = None
        else:
            signal_row = await conn.fetchrow(
                """
                INSERT INTO public.saved_jobs (applicant_id, job_id, interest_level)
                VALUES ($1, $2::uuid, $3)
                ON CONFLICT (applicant_id, job_id)
                DO UPDATE SET interest_level = EXCLUDED.interest_level, updated_at = NOW()
                RETURNING interest_level, saved_jobs.updated_at::text
                """,
                applicant_id, job_id, body.interest_level,
            )

        changed = prev_level != body.interest_level
        if changed:
            # State write + analytics event commit together (moment of truth).
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO public.engagement_events (applicant_id, job_id, event_type, event_data)
                    VALUES ($1, $2::uuid, 'interest_set', $3::jsonb)
                    """,
                    applicant_id,
                    job_id,
                    {"interest_level": body.interest_level, "match_id": match_id,
                     "previous_level": prev_level},
                )
                # Additionally log apply_click when applicant marks themselves as applied
                if body.interest_level == "applied":
                    await conn.execute(
                        """
                        INSERT INTO public.engagement_events (applicant_id, job_id, event_type, event_data)
                        VALUES ($1, $2::uuid, 'apply_click', $3::jsonb)
                        """,
                        applicant_id,
                        job_id,
                        {"match_id": match_id, "source": "self_reported"},
                    )

    return InterestSignalResponse(
        match_id=match_id,
        job_id=job_id,
        interest_level=signal_row["interest_level"] if signal_row else None,
        updated_at=signal_row["updated_at"] if signal_row else None,
    )


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
    # Use get_settings() (not os.environ) so the key loads from .env like the
    # rest of the app — os.environ.get would silently return None and disable
    # this fallback in any env that relies on the .env file.
    from app.config import get_settings
    api_key = get_settings().openai_api_key
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

        from app.util.openai_client import interactive_http_timeout
        async with httpx.AsyncClient(timeout=interactive_http_timeout()) as client:
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
