"""
scorer.py — structured scoring engine.

Implements the 9 scoring dimensions from SCORING_CONFIG.yaml §structured_score.
All functions are pure — they receive normalized data and return DimensionScore objects.

Null handling follows DECISIONS.md §2.6 / SCORING_CONFIG.yaml §null_handling:
  - missing data defaults to NEUTRAL, not punitive
  - unknown compensation → 70
  - unknown credentials (non-required) → 50
  - unknown geography → 35 (fully) or 50 (partial)
  - unknown experience → 50

Dimension weights (defaulted, from SCORING_CONFIG.yaml):
  trade_program_alignment:         25
  geography_alignment:             20
  credential_readiness:            15
  timing_readiness:                10
  experience_internship_alignment: 10
  industry_alignment:               5
  compensation_alignment:           5
  work_style_signal_alignment:      5
  employer_soft_pref_alignment:     5
  Total = 100
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import ScoringConfig
from .normalizer import TimingResult, JOB_FAMILY_ADJACENCY


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DimensionScore:
    dimension: str
    weight: float
    raw_score: float         # 0–100 score for this dimension
    weighted_score: float    # weight * raw_score / 100
    rationale: str
    null_handling_applied: bool = False
    null_handling_default: float | None = None


# ---------------------------------------------------------------------------
# Individual dimension scorers
# ---------------------------------------------------------------------------

def score_trade_program_alignment(
    applicant_family_code: str | None,
    job_family_code: str | None,
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Trade/program alignment (weight 25).
    Direct match → 100, adjacent → 60, unrelated → 20, unknown → null default.
    """
    adjacent = JOB_FAMILY_ADJACENCY.get(applicant_family_code or "", set())

    if applicant_family_code is None or job_family_code is None:
        return DimensionScore(
            "trade_program_alignment", weight,
            null_default, weight * null_default / 100,
            "program or job family not yet normalised — using null default",
            True, null_default,
        )

    if applicant_family_code == job_family_code:
        s, r = 100.0, f"direct family match: {applicant_family_code}"
    elif job_family_code in adjacent:
        s, r = 60.0, f"adjacent families: applicant={applicant_family_code}, job={job_family_code}"
    else:
        s, r = 20.0, f"unrelated families: applicant={applicant_family_code}, job={job_family_code}"

    return DimensionScore("trade_program_alignment", weight, s, weight * s / 100, r)


def score_geography_alignment(
    applicant_state: str | None,
    applicant_region: str | None,
    willing_to_relocate: bool,
    willing_to_travel: bool,
    job_state: str | None,
    job_region: str | None,
    job_work_setting: str | None,
    weight: float,
    null_handling,   # NullHandlingConfig
) -> DimensionScore:
    """
    Geography alignment (weight 20).
    Remote → 90, same state → 100, same region+willing → 80,
    diff region+willing → 55, infeasible → 20, unknown → config defaults.
    """
    dim = "geography_alignment"
    ws = (job_work_setting or "").lower()

    if ws == "remote":
        s, r = 90.0, "fully remote job — geography not a constraint"
        return DimensionScore(dim, weight, s, weight * s / 100, r)

    if not applicant_state and not job_state:
        s = null_handling.geography_fully_unknown
        r = "no location data for either party — fully unknown"
        return DimensionScore(dim, weight, s, weight * s / 100, r, True, s)

    if applicant_state and job_state and applicant_state.upper() == job_state.upper():
        s, r = 100.0, f"same state: {applicant_state}"
    elif applicant_region and job_region and applicant_region == job_region:
        if willing_to_relocate or willing_to_travel:
            s, r = 80.0, f"same region ({applicant_region}), willing to relocate/travel"
        else:
            s = null_handling.geography_partially_known
            r = f"same region ({applicant_region}), relocation willingness unknown"
            return DimensionScore(dim, weight, s, weight * s / 100, r, True, s)
    elif willing_to_relocate:
        s, r = 55.0, f"different region but willing to relocate (applicant={applicant_state}, job={job_state})"
    elif not applicant_state or not job_state:
        s = null_handling.geography_partially_known
        r = "partial location data"
        return DimensionScore(dim, weight, s, weight * s / 100, r, True, s)
    else:
        s, r = 20.0, f"geography mismatch: {applicant_state}/{applicant_region} → {job_state}/{job_region}"

    return DimensionScore(dim, weight, s, weight * s / 100, r)


def score_credential_readiness(
    required_credentials: list[str] | None,
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Credential readiness (weight 15).
    No required credentials → 80 (neutral-good: job is accessible).
    Required + extraction pending → null default (50).
    Phase 7 will make this dimension precise.
    """
    dim = "credential_readiness"
    if not required_credentials:
        s, r = 80.0, "no explicit credential requirements on job"
        return DimensionScore(dim, weight, s, weight * s / 100, r)

    s = null_default
    cred_list = ", ".join(required_credentials[:2])
    r = f"required credentials [{cred_list}] not yet verified — Phase 7 pending"
    return DimensionScore(dim, weight, s, weight * s / 100, r, True, s)


def score_timing_readiness(
    timing: TimingResult,
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Timing readiness (weight 10).
    available_now → 100, near_completion → 90, in_progress → scales 40–75,
    future → 20, unknown → null default.
    """
    dim = "timing_readiness"
    if timing.readiness_label == "available_now":
        s, r = 100.0, "applicant is available now"
    elif timing.readiness_label == "near_completion":
        s, r = 90.0, f"near completion (~{timing.months_to_available} months)"
    elif timing.readiness_label == "in_progress":
        months = timing.months_to_available or 0
        # Linear scale: 4 months → 75, 12 months → 40
        s = max(40.0, 75.0 - (months - 4) * (35.0 / 8.0))
        r = f"in progress (~{months} months to available)"
    elif timing.readiness_label == "future":
        s, r = 20.0, f"materially delayed (~{timing.months_to_available} months)"
    else:
        s = null_default
        r = "no timing information — null default"
        return DimensionScore(dim, weight, s, weight * s / 100, r, True, s)

    return DimensionScore(dim, weight, s, weight * s / 100, r)


def score_experience_alignment(
    experience_raw: str | None,
    bio_raw: str | None,
    internship_completed: bool | None,
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Experience + internship alignment (weight 10).
    experience text + internship → 85, experience only → 65,
    bio/essay only → 55, nothing → null default.
    """
    dim = "experience_internship_alignment"
    has_exp = bool(experience_raw and len(experience_raw.strip()) > 20)
    has_bio = bool(bio_raw and len(bio_raw.strip()) > 20)
    has_internship = internship_completed is True

    if has_exp and has_internship:
        s, r = 85.0, "experience details + completed internship"
    elif has_exp:
        s, r = 65.0, "experience/internship details present"
    elif has_bio:
        s, r = 55.0, "personal statement / bio present (limited direct experience signal)"
    else:
        s = null_default
        r = "no experience data — null default"
        return DimensionScore(dim, weight, s, weight * s / 100, r, True, s)

    return DimensionScore(dim, weight, s, weight * s / 100, r)


def score_industry_alignment(
    applicant_family_code: str | None,
    job_family_code: str | None,
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Industry-level alignment (weight 5).
    Coarser than trade_program_alignment — same or adjacent = good.
    Same family → 80, adjacent → 65, unrelated → 30, unknown → null default.
    """
    dim = "industry_alignment"
    adjacent = JOB_FAMILY_ADJACENCY.get(applicant_family_code or "", set())

    if applicant_family_code is None or job_family_code is None:
        return DimensionScore(dim, weight, null_default, weight * null_default / 100,
                              "unknown family — null default", True, null_default)

    if applicant_family_code == job_family_code:
        s, r = 80.0, f"same industry: {applicant_family_code}"
    elif job_family_code in adjacent:
        s, r = 65.0, f"adjacent industry: {applicant_family_code} / {job_family_code}"
    else:
        s, r = 30.0, f"different industry: applicant={applicant_family_code}, job={job_family_code}"

    return DimensionScore(dim, weight, s, weight * s / 100, r)


def score_compensation_alignment(
    job_pay_min: float | None,
    job_pay_max: float | None,
    job_pay_type: str | None,
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Compensation alignment (weight 5).
    Applicant expected salary is not in the SkillPointe import → default to neutral.
    If job has pay data, slight boost for competitive wages.
    Phase 7 may extract desired salary from essays.
    """
    dim = "compensation_alignment"
    if job_pay_min is None:
        return DimensionScore(dim, weight, null_default, weight * null_default / 100,
                              "no pay data on job — null default", True, null_default)

    avg = (job_pay_min + (job_pay_max or job_pay_min)) / 2
    pay_label = job_pay_type or "unknown"

    if job_pay_type == "hourly" and avg >= 20:
        s, r = 75.0, f"competitive hourly pay: ${job_pay_min}–${job_pay_max or job_pay_min}/hr"
    elif job_pay_type == "annual" and avg >= 40_000:
        s, r = 75.0, f"competitive salary: ${job_pay_min:,.0f}–${job_pay_max or job_pay_min:,.0f}/yr"
    else:
        s = null_default
        r = f"pay data present but below competitive threshold: {pay_label} avg ${avg:.0f}"
        return DimensionScore(dim, weight, s, weight * s / 100, r, True, s)

    return DimensionScore(dim, weight, s, weight * s / 100, r)


def score_work_style_alignment(
    job_work_setting: str | None,
    job_travel_requirement: str | None,
    willing_to_travel: bool,
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Work style / setting alignment (weight 5).
    Remote → 80, hybrid → 72, on-site (no heavy travel) → 75,
    heavy travel + unwilling → 40, unknown → null default.
    """
    dim = "work_style_signal_alignment"
    ws = (job_work_setting or "").lower()
    travel = (job_travel_requirement or "").lower()

    if not ws:
        return DimensionScore(dim, weight, null_default, weight * null_default / 100,
                              "no work setting info — null default", True, null_default)

    if ws == "remote":
        s, r = 80.0, "fully remote"
    elif ws == "hybrid":
        s, r = 72.0, "hybrid work setting"
    elif ws == "on_site":
        if "frequent" in travel or "heavy" in travel:
            if willing_to_travel:
                s, r = 65.0, "on-site with frequent travel — willing"
            else:
                s, r = 40.0, "on-site with frequent travel — not willing"
        else:
            s, r = 75.0, "on-site (standard)"
    elif ws == "flexible":
        s, r = 75.0, "flexible work arrangement"
    else:
        return DimensionScore(dim, weight, null_default, weight * null_default / 100,
                              f"unrecognised setting '{ws}' — null default", True, null_default)

    return DimensionScore(dim, weight, s, weight * s / 100, r)


def score_employer_soft_pref(
    weight: float,
    null_default: float,
) -> DimensionScore:
    """
    Employer soft preference alignment (weight 5).
    Pre-Phase-7: no explicit soft preferences extracted → null default (50).
    """
    dim = "employer_soft_pref_alignment"
    return DimensionScore(
        dim, weight, null_default, weight * null_default / 100,
        "employer soft preferences not yet extracted — Phase 7 pending",
        True, null_default,
    )


# ---------------------------------------------------------------------------
# Aggregate structured score
# ---------------------------------------------------------------------------

def compute_structured_score(
    applicant: dict[str, Any],
    job: dict[str, Any],
    timing: TimingResult,
    config: ScoringConfig,
) -> tuple[float, list[DimensionScore]]:
    """
    Compute the full weighted structured score (0–100) and per-dimension breakdown.

    applicant / job dicts must have the canonical_job_family_code field set
    (populated by normalize_data.py — joined from canonical_job_families table).

    Returns:
        (weighted_structured_score, dimension_scores)
    """
    w = config.structured_weights
    nh = config.null_handling

    app_family = applicant.get("canonical_job_family_code")
    job_family = job.get("canonical_job_family_code")

    # internship_completed may be in raw_data / extra — use experience_raw as proxy
    internship_completed: bool | None = None  # Phase 7 will extract this

    dimensions: list[DimensionScore] = [
        score_trade_program_alignment(
            app_family, job_family,
            w.trade_program_alignment, nh.credentials_unknown_nonrequired,
        ),
        score_geography_alignment(
            applicant.get("state"), applicant.get("region"),
            bool(applicant.get("willing_to_relocate")),
            bool(applicant.get("willing_to_travel")),
            job.get("state"), job.get("region"),
            job.get("work_setting"),
            w.geography_alignment, nh,
        ),
        score_credential_readiness(
            job.get("required_credentials") or [],
            w.credential_readiness, nh.credentials_unknown_nonrequired,
        ),
        score_timing_readiness(timing, w.timing_readiness, nh.experience_unknown),
        score_experience_alignment(
            applicant.get("experience_raw"),
            applicant.get("bio_raw"),
            internship_completed,
            w.experience_internship_alignment, nh.experience_unknown,
        ),
        score_industry_alignment(
            app_family, job_family,
            w.industry_alignment, 50.0,
        ),
        score_compensation_alignment(
            job.get("pay_min"), job.get("pay_max"), job.get("pay_type"),
            w.compensation_alignment, nh.compensation_alignment_unknown,
        ),
        score_work_style_alignment(
            job.get("work_setting"), job.get("travel_requirement"),
            bool(applicant.get("willing_to_travel")),
            w.work_style_signal_alignment, nh.work_style_signal_alignment_unknown,
        ),
        score_employer_soft_pref(
            w.employer_soft_pref_alignment, nh.employer_soft_pref_alignment_unknown,
        ),
    ]

    # Each weighted_score = weight * raw / 100
    # Sum of weights = 100, so max total = sum(w_i * 100 / 100) = 100
    total = sum(d.weighted_score for d in dimensions)
    weighted_structured_score = round(min(100.0, max(0.0, total)), 2)

    return weighted_structured_score, dimensions
