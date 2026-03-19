"""
Pydantic response schemas for applicant-side API endpoints (Phase 6.1).

Key design rules (DECISIONS.md / SCORING_CONFIG.yaml):
  - Display score: policy_adjusted_score (per §ui_visibility)
  - base_fit_score stored separately, shown in detail view only
  - Two labeled sections: eligible ("best immediate") / near_fit ("promising near-fit")
  - Ineligible matches hidden from applicant by default
  - Geography is first-class in every response
"""
from __future__ import annotations
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class ApplicantProfileSummary(BaseModel):
    applicant_id: str
    first_name: str | None
    last_name: str | None
    program_name_raw: str | None
    canonical_job_family_code: str | None
    city: str | None
    state: str | None
    region: str | None
    willing_to_relocate: bool
    willing_to_travel: bool
    expected_completion_date: str | None
    available_from_date: str | None
    profile_completeness: int   # 0–100 rough percentage

    # Expanded fields
    enrollment_status: str | None
    degree_type: str | None
    school_name: str | None
    school_city: str | None
    school_state: str | None
    career_path: str | None
    program_field: str | None
    specific_career: str | None
    program_start_date: str | None
    gpa: float | None

    travel_preference: str | None
    relocation_preference: str | None
    relocation_states: list[str]

    age_range: str | None
    gender: str | None
    military_status: bool
    military_dependent: bool
    current_wages: str | None
    has_internship: bool
    activities: str | None
    honor_societies: list[str]


# ---------------------------------------------------------------------------
# Match list items
# ---------------------------------------------------------------------------

class JobMatchSummary(BaseModel):
    match_id: str
    job_id: str
    job_title: str                  # title_normalized or title_raw fallback
    employer_name: str
    is_partner_employer: bool

    # Geography (first-class)
    job_city: str | None
    job_state: str | None
    job_region: str | None
    work_setting: str | None        # remote / hybrid / on_site / flexible
    travel_requirement: str | None
    geography_note: str | None      # derived human-readable note

    # Pay
    pay_min: float | None
    pay_max: float | None
    pay_type: str | None            # hourly / annual

    # Score and label (DECISIONS.md §ui: display policy_adjusted_score)
    eligibility_status: str         # eligible / near_fit
    match_label: str | None         # strong_fit / good_fit / moderate_fit / low_fit
    policy_adjusted_score: float | None

    # Explanation
    top_strengths: list[str]
    top_gaps: list[str]
    recommended_next_step: str | None

    # Application
    source_url: str | None
    canonical_job_family_code: str | None

    # Job detail (for expandable card)
    description_raw: str | None
    requirements_raw: str | None
    preferred_qualifications_raw: str | None
    experience_level: str | None

    # Confidence
    confidence_level: str | None
    requires_review: bool


# ---------------------------------------------------------------------------
# Match detail (extends summary)
# ---------------------------------------------------------------------------

class DimensionScoreItem(BaseModel):
    dimension: str
    weight: float
    raw_score: float
    weighted_score: float
    rationale: str | None
    null_handling_applied: bool
    null_handling_default: float | None


class GateResultItem(BaseModel):
    gate_name: str
    result: str          # pass / near_fit / fail
    reason: str
    severity: str | None


class PolicyModifierItem(BaseModel):
    policy: str
    value: float
    reason: str


class JobMatchDetail(JobMatchSummary):
    # Additional score layers (detail view only)
    base_fit_score: float | None
    weighted_structured_score: float | None
    semantic_score: float | None

    # Mandatory gaps (hard failures)
    required_missing_items: list[str]

    # Gate breakdown
    hard_gate_rationale: list[GateResultItem]

    # Policy adjustments
    policy_modifiers: list[PolicyModifierItem]

    # Dimension scores (9 rows)
    dimension_scores: list[DimensionScoreItem]


# ---------------------------------------------------------------------------
# Ranked matches response (two-section applicant view)
# ---------------------------------------------------------------------------

class RankedMatchesResponse(BaseModel):
    applicant_id: str

    # Section 1: "Best immediate opportunities" — eligible only
    eligible_matches: list[JobMatchSummary]
    total_eligible: int

    # Section 2: "Promising near-fit opportunities" — near_fit only
    near_fit_matches: list[JobMatchSummary]
    total_near_fit: int

    has_matches: bool
    profile_has_family: bool    # job family normalised
    profile_has_location: bool  # state / region set
