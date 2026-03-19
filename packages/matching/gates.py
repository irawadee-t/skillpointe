"""
gates.py — deterministic hard eligibility gate engine.

Implements the five gates from SCORING_CONFIG.yaml §eligibility.rules.
Each gate returns a GateDetail (PASS / NEAR_FIT / FAIL + rationale).
The final eligibility label is determined by the worst single-gate result.

Gate results per SCORING_CONFIG.yaml:
  PASS     → no issue
  NEAR_FIT → important gap, but pair is still worth surfacing
  FAIL     → critical mismatch

Final label aggregation (DECISIONS.md 1.11, 1.12):
  Any FAIL     → ineligible (cap 0.35)
  Any NEAR_FIT → near_fit   (cap 0.75)
  All PASS     → eligible   (cap 1.0)

DECISIONS.md 1.12 hard rule:
  No pair may be labeled high fit if a critical hard gate fails.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .normalizer import TimingResult, JOB_FAMILY_ADJACENCY

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PASS = "pass"
NEAR_FIT = "near_fit"
FAIL = "fail"

ELIGIBLE = "eligible"
NEAR_FIT_LABEL = "near_fit"
INELIGIBLE = "ineligible"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GateDetail:
    gate_name: str
    result: str           # PASS, NEAR_FIT, or FAIL
    reason: str
    severity: str = "normal"   # 'critical', 'normal', 'advisory'
    needs_review: bool = False


@dataclass
class EligibilityResult:
    eligibility_status: str    # ELIGIBLE, NEAR_FIT_LABEL, INELIGIBLE
    hard_gate_cap: float
    gate_details: list[GateDetail] = field(default_factory=list)

    @property
    def hard_gate_failures(self) -> list[dict]:
        return [
            {"gate": g.gate_name, "reason": g.reason, "severity": g.severity}
            for g in self.gate_details if g.result == FAIL
        ]

    @property
    def hard_gate_rationale(self) -> dict:
        return {
            g.gate_name: {"result": g.result, "reason": g.reason}
            for g in self.gate_details
        }

    @property
    def requires_review(self) -> bool:
        return any(g.needs_review for g in self.gate_details)


# ---------------------------------------------------------------------------
# Gate 1: Job family compatibility
# ---------------------------------------------------------------------------

def evaluate_job_family_gate(
    applicant_family_code: str | None,
    job_family_code: str | None,
) -> GateDetail:
    """
    Gate 1: Does the applicant's trade/program match the job's family?

    Direct match → PASS
    Adjacent family → NEAR_FIT
    Unrelated → FAIL
    Either unknown → NEAR_FIT (null handling — cannot confirm incompatibility)
    """
    if applicant_family_code is None or job_family_code is None:
        return GateDetail(
            "job_family_compatibility", NEAR_FIT,
            "one or both family codes unknown — cannot confirm compatibility",
            needs_review=True,
        )

    if applicant_family_code == job_family_code:
        return GateDetail(
            "job_family_compatibility", PASS,
            f"direct match: {applicant_family_code}",
        )

    adjacent = JOB_FAMILY_ADJACENCY.get(applicant_family_code, set())
    if job_family_code in adjacent:
        return GateDetail(
            "job_family_compatibility", NEAR_FIT,
            f"adjacent families: applicant={applicant_family_code}, job={job_family_code}",
        )

    return GateDetail(
        "job_family_compatibility", FAIL,
        f"unrelated families: applicant={applicant_family_code}, job={job_family_code}",
        severity="critical",
    )


# ---------------------------------------------------------------------------
# Gate 2: Required credential compatibility
# ---------------------------------------------------------------------------

def evaluate_credential_gate(
    required_credentials: list[str] | None,
    applicant: dict[str, Any],
    applicant_certs: list[str] | None = None,
    job_min_education: str | None = None,
    applicant_education: str | None = None,
    job_required_experience_years: int | None = None,
    education_or_equivalent: bool = False,
) -> GateDetail:
    """
    Gate 2: Does the applicant meet the job's required credentials/licenses/education?

    Checks three dimensions:
      A) Education level compatibility (bachelor's, associate's, trade cert, etc.)
         — respects "or equivalent experience" clauses common in job descriptions
      B) Specific credential/license matching (CDL, EPA 608, etc.)
      C) Experience year requirements (from structured field)

    The worst result across all three determines the gate outcome.
    """
    sub_results: list[tuple[str, str, str]] = []  # (result, reason, severity)

    # --- A) Education level check ---
    _EDU_RANK = {"high_school": 1, "military": 2, "trade_cert": 3, "associates": 4, "bachelors": 5}

    if job_min_education and applicant_education:
        job_rank = _EDU_RANK.get(job_min_education, 2)
        app_rank = _EDU_RANK.get(applicant_education, 2)

        if app_rank >= job_rank:
            sub_results.append((PASS, f"education: applicant has {applicant_education}, job requires {job_min_education}", "normal"))
        elif education_or_equivalent and app_rank >= job_rank - 1:
            # "Associate's degree OR equivalent experience" — trade cert counts
            sub_results.append((PASS, f"education: {applicant_education} accepted (job says 'or equivalent')", "normal"))
        elif education_or_equivalent and app_rank >= job_rank - 2:
            sub_results.append((NEAR_FIT, f"education: job prefers {job_min_education} or equivalent, applicant has {applicant_education}", "normal"))
        elif app_rank >= job_rank - 1:
            sub_results.append((NEAR_FIT, f"education close: applicant has {applicant_education}, job prefers {job_min_education}", "normal"))
        else:
            sub_results.append((FAIL, f"education mismatch: job requires {job_min_education}, applicant has {applicant_education}", "critical"))
    elif job_min_education:
        sub_results.append((NEAR_FIT, f"job requires {job_min_education} — applicant education unknown", "normal"))

    # --- B) Specific credentials check ---
    if required_credentials:
        cred_list = ", ".join(required_credentials[:3])
        cred_count = len(required_credentials)

        if applicant_certs is not None:
            app_certs_lower = {c.lower().strip() for c in applicant_certs}
            matched = []
            unmatched = []
            for req in required_credentials:
                req_lower = req.lower().strip()
                if any(req_lower in ac or ac in req_lower for ac in app_certs_lower):
                    matched.append(req)
                else:
                    unmatched.append(req)

            if not unmatched:
                sub_results.append((PASS, f"all {cred_count} credentials matched", "normal"))
            elif matched:
                sub_results.append((NEAR_FIT, f"partial credential match — has [{', '.join(matched)}], missing [{', '.join(unmatched)}]", "normal"))
            else:
                sub_results.append((FAIL, f"required credentials [{cred_list}] not found", "critical"))
        else:
            sub_results.append((NEAR_FIT, f"requires [{cred_list}] — applicant credentials not yet verified", "normal"))

    # --- C) Experience years check ---
    if job_required_experience_years is not None and job_required_experience_years > 0:
        app_exp = applicant.get("years_experience") or 0
        if app_exp >= job_required_experience_years:
            sub_results.append((PASS, f"experience: applicant has {app_exp}+ yrs, job needs {job_required_experience_years}", "normal"))
        elif job_required_experience_years <= 1:
            # 1 year: trade school training often accepted as equivalent
            sub_results.append((PASS, f"job prefers {job_required_experience_years} yr experience — trade school training typically qualifies", "normal"))
        elif job_required_experience_years == 2:
            sub_results.append((NEAR_FIT, f"job needs {job_required_experience_years} yrs experience — new graduate may qualify", "normal"))
        elif job_required_experience_years <= 4:
            # 3-4 years: significant gap for a new grad (journeyman territory)
            sub_results.append((FAIL, f"job requires {job_required_experience_years}+ years experience — requires substantial field time", "critical"))
        else:
            sub_results.append((FAIL, f"job requires {job_required_experience_years}+ years experience — significant gap for new graduate", "critical"))

    # --- Aggregate: worst sub-result wins ---
    if not sub_results:
        return GateDetail(
            "required_credential_compatibility", PASS,
            "no explicit credential, education, or experience requirements on job",
        )

    has_fail = any(r[0] == FAIL for r in sub_results)
    has_near = any(r[0] == NEAR_FIT for r in sub_results)

    if has_fail:
        fail_reasons = [r[1] for r in sub_results if r[0] == FAIL]
        return GateDetail(
            "required_credential_compatibility", FAIL,
            "; ".join(fail_reasons),
            severity="critical",
        )
    if has_near:
        # Only include non-PASS reasons — PASS sub-results are not gaps
        gap_reasons = [r[1] for r in sub_results if r[0] != PASS]
        if not gap_reasons:
            gap_reasons = [r[1] for r in sub_results]
        return GateDetail(
            "required_credential_compatibility", NEAR_FIT,
            "; ".join(gap_reasons),
        )
    pass_reasons = [r[1] for r in sub_results]
    return GateDetail(
        "required_credential_compatibility", PASS,
        "; ".join(pass_reasons),
    )


# ---------------------------------------------------------------------------
# Gate 3: Readiness / timing compatibility
# ---------------------------------------------------------------------------

def evaluate_timing_gate(timing: TimingResult) -> GateDetail:
    """
    Gate 3: Is the applicant's timeline compatible with the job?

    available_now        → PASS
    near_completion (<4m)→ PASS (within hiring window)
    in_progress (4–24m)  → NEAR_FIT
    future (>24m)        → FAIL
    unknown              → PASS (null handling)
    """
    if timing.readiness_label == "unknown":
        return GateDetail(
            "readiness_timing_compatibility", PASS,
            "timing not specified — assumed available",
        )

    if timing.readiness_label == "available_now":
        return GateDetail(
            "readiness_timing_compatibility", PASS,
            "applicant is available now",
        )

    if timing.readiness_label in ("near_completion", "in_progress"):
        months = timing.months_to_available or 0
        # 3 months or less: employers regularly hire ahead — count as available
        if months <= 3:
            return GateDetail(
                "readiness_timing_compatibility", PASS,
                f"completing program in ~{months} month(s) — within typical hiring window",
            )
        return GateDetail(
            "readiness_timing_compatibility", NEAR_FIT,
            f"completing program in ~{months} months",
        )

    # future — materially delayed (>24 months)
    months = timing.months_to_available or 0
    return GateDetail(
        "readiness_timing_compatibility", FAIL,
        f"materially delayed: available in ~{months} months (threshold: 24)",
        severity="critical",
    )


# ---------------------------------------------------------------------------
# Gate 4: Geography feasibility
# ---------------------------------------------------------------------------

def evaluate_geography_gate(
    applicant_state: str | None,
    applicant_region: str | None,
    willing_to_relocate: bool,
    willing_to_travel: bool,
    job_state: str | None,
    job_region: str | None,
    job_work_setting: str | None,
    relocation_preference: str | None = None,
    relocation_states: list[str] | None = None,
    travel_preference: str | None = None,
) -> GateDetail:
    """
    Gate 4: Is the geography feasible?

    Uses granular travel_preference and relocation_preference enums:
      travel_preference:     no_travel | within_state | regional | nationwide
      relocation_preference: stay_current | within_state | within_region | anywhere

    Decision matrix (after remote/same-state checks):
                          | Same region, diff state  | Different region
      ──────────────────────────────────────────────────────────────────
      relocate=anywhere    | PASS                     | PASS
      relocate=in_region   | PASS                     | NEAR_FIT
      travel=nationwide    | PASS                     | NEAR_FIT
      travel=regional      | PASS                     | FAIL
      relocate=in_state    | NEAR_FIT                 | FAIL
      travel=within_state  | NEAR_FIT                 | FAIL
      stay_current+no_trvl | FAIL                     | FAIL
    """
    ws = (job_work_setting or "").lower()

    if ws == "remote":
        return GateDetail(
            "geography_feasibility", PASS,
            "fully remote job — geography not a constraint",
        )

    if not job_state:
        return GateDetail(
            "geography_feasibility", PASS,
            "job location not specified — geography not assessed",
        )

    app_upper = (applicant_state or "").upper()
    job_upper = (job_state or "").upper()
    app_region_lower = (applicant_region or "").lower()
    job_region_lower = (job_region or "").lower()

    # Same state is always fine
    if app_upper and job_upper and app_upper == job_upper:
        return GateDetail(
            "geography_feasibility", PASS,
            f"same state: {applicant_state}",
        )

    # Job in explicitly chosen relocation states
    if relocation_states and job_state:
        reloc_upper = {s.upper() for s in relocation_states}
        if job_upper in reloc_upper:
            return GateDetail(
                "geography_feasibility", PASS,
                f"job is in applicant's chosen relocation state: {job_state}",
            )

    # Derive effective willingness from enums (falling back to booleans)
    r_pref = relocation_preference or ("anywhere" if willing_to_relocate else "stay_current")
    t_pref = travel_preference or ("regional" if willing_to_travel else "no_travel")

    same_region = bool(app_region_lower and job_region_lower
                       and app_region_lower == job_region_lower)

    loc_desc = f"applicant={applicant_state}/{applicant_region}, job={job_state}/{job_region}"

    if same_region:
        # Same region, different state
        if r_pref in ("anywhere", "within_region", "specific_states"):
            return GateDetail(
                "geography_feasibility", PASS,
                f"same region ({applicant_region}), open to relocating within region",
            )
        if t_pref in ("regional", "within_region", "nationwide", "anywhere"):
            return GateDetail(
                "geography_feasibility", PASS,
                f"same region ({applicant_region}), willing to travel regionally",
            )
        if t_pref == "within_state" or r_pref == "within_state":
            return GateDetail(
                "geography_feasibility", NEAR_FIT,
                f"same region but different state — {loc_desc} (prefers in-state)",
            )
        return GateDetail(
            "geography_feasibility", FAIL,
            f"same region but different state — {loc_desc} (not willing to relocate/travel out of state)",
            severity="critical",
        )

    # Different region
    if r_pref == "anywhere":
        return GateDetail(
            "geography_feasibility", NEAR_FIT,
            f"different region but open to relocating anywhere — {loc_desc}",
        )
    if t_pref in ("nationwide", "anywhere"):
        return GateDetail(
            "geography_feasibility", NEAR_FIT,
            f"different region but willing to travel nationwide — {loc_desc}",
        )
    if r_pref in ("within_region", "within_state"):
        return GateDetail(
            "geography_feasibility", NEAR_FIT,
            f"different region — {loc_desc} (would require relocation; prefers {r_pref.replace('_', ' ')})",
        )

    if not applicant_state:
        return GateDetail(
            "geography_feasibility", NEAR_FIT,
            "applicant location not set — please update your profile",
            needs_review=True,
        )

    return GateDetail(
        "geography_feasibility", NEAR_FIT,
        f"different location — {loc_desc} (would require relocation)",
    )


# ---------------------------------------------------------------------------
# Gate 5: Explicit minimum requirement compatibility
# ---------------------------------------------------------------------------

def evaluate_min_req_gate(
    applicant: dict[str, Any],
    job_description_raw: str | None,
    applicant_skills: list[str] | None = None,
    job_critical_skills: list[str] | None = None,
) -> GateDetail:
    """
    Gate 5: Does the applicant meet explicit minimum requirements?

    When extracted signals are available, compares applicant skills against
    job critical/required skills. Otherwise falls back to null-handling.
    """
    if not job_description_raw:
        return GateDetail(
            "explicit_minimum_requirement_compatibility", PASS,
            "no job description to evaluate against",
        )

    # Phase 7 path: extracted skills available for both sides
    if applicant_skills is not None and job_critical_skills is not None:
        if not job_critical_skills:
            return GateDetail(
                "explicit_minimum_requirement_compatibility", PASS,
                "no critical skill requirements extracted from job",
            )

        app_skills_lower = {s.lower().strip() for s in applicant_skills}
        matched = []
        unmatched = []
        for req in job_critical_skills:
            req_lower = req.lower().strip()
            if any(req_lower in ask or ask in req_lower for ask in app_skills_lower):
                matched.append(req)
            else:
                unmatched.append(req)

        if not unmatched:
            return GateDetail(
                "explicit_minimum_requirement_compatibility", PASS,
                f"all critical skills matched: {', '.join(matched[:3])}",
            )
        ratio = len(matched) / (len(matched) + len(unmatched))
        if ratio >= 0.5:
            return GateDetail(
                "explicit_minimum_requirement_compatibility", NEAR_FIT,
                f"partial skill match ({len(matched)}/{len(matched)+len(unmatched)}) — "
                f"missing: {', '.join(unmatched[:3])}",
            )
        return GateDetail(
            "explicit_minimum_requirement_compatibility", FAIL,
            f"missing critical skills: {', '.join(unmatched[:3])}",
            severity="critical",
        )

    # Fallback: no extraction data — PASS, not NEAR_FIT.
    # Absence of extraction evidence is not evidence of missing requirements.
    # Gate 1 (job family) already screens for fundamental mismatch.
    # Mark needs_review so admin can prioritize running extraction.
    return GateDetail(
        "explicit_minimum_requirement_compatibility", PASS,
        "minimum requirements not yet extracted — defaulting to pass (no evidence of mismatch)",
        needs_review=True,
    )


# ---------------------------------------------------------------------------
# Gate 6: Seniority / experience level compatibility
# ---------------------------------------------------------------------------

def evaluate_seniority_gate(
    job_experience_level: str | None,
    applicant_experience_years: int | None,
    is_trade_school: bool = True,
) -> GateDetail:
    """
    Gate 6: Is the job's seniority level appropriate for this applicant?

    Trade school graduates are typically entry-level. Senior/management
    roles that need 5+ years are inappropriate matches.

    entry job       → PASS
    mid job         → NEAR_FIT if trade school, PASS if experienced
    senior job      → FAIL if trade school with < 3 years
    management job  → FAIL for trade school applicants
    """
    level = (job_experience_level or "entry").lower()

    if level == "entry":
        return GateDetail(
            "seniority_compatibility", PASS,
            "entry-level position — appropriate for trade school graduates",
        )

    exp_years = applicant_experience_years or 0

    if level == "mid":
        if exp_years >= 2:
            return GateDetail(
                "seniority_compatibility", PASS,
                f"mid-level position, applicant has {exp_years}+ years experience",
            )
        if is_trade_school:
            return GateDetail(
                "seniority_compatibility", NEAR_FIT,
                "mid-level position — may require more experience than a recent graduate has",
            )
        return GateDetail(
            "seniority_compatibility", NEAR_FIT,
            "mid-level position — experience level uncertain",
        )

    if level == "senior":
        if exp_years >= 5:
            return GateDetail(
                "seniority_compatibility", PASS,
                f"senior position, applicant has {exp_years}+ years",
            )
        if exp_years >= 3:
            return GateDetail(
                "seniority_compatibility", NEAR_FIT,
                f"senior position — applicant has {exp_years} years (may be stretch)",
            )
        return GateDetail(
            "seniority_compatibility", FAIL,
            "senior-level position requires significant experience — not suitable for recent graduates",
            severity="critical",
        )

    if level == "management":
        if exp_years >= 5:
            return GateDetail(
                "seniority_compatibility", NEAR_FIT,
                f"management position — applicant has {exp_years} years but management experience unclear",
            )
        return GateDetail(
            "seniority_compatibility", FAIL,
            "management position requires leadership experience — not suitable for recent graduates",
            severity="critical",
        )

    return GateDetail(
        "seniority_compatibility", PASS,
        f"unknown experience level '{level}' — defaulting to pass",
    )


# ---------------------------------------------------------------------------
# Final eligibility aggregation
# ---------------------------------------------------------------------------

def compute_eligibility(
    gate_details: list[GateDetail],
    caps_config=None,
) -> EligibilityResult:
    """
    Aggregate all gate results into a final eligibility label and cap multiplier.

    Per DECISIONS.md 1.11:
      Any FAIL     → ineligible (cap 0.35)
      Any NEAR_FIT → near_fit   (cap 0.75)
      All PASS     → eligible   (cap 1.0)

    Per DECISIONS.md 1.12:
      No pair labeled high fit if a critical hard gate fails.
    """
    from .config import EligibilityCapConfig
    caps = caps_config or EligibilityCapConfig()

    has_fail = any(g.result == FAIL for g in gate_details)
    has_near_fit = any(g.result == NEAR_FIT for g in gate_details)

    if has_fail:
        return EligibilityResult(INELIGIBLE, caps.ineligible, gate_details)
    if has_near_fit:
        return EligibilityResult(NEAR_FIT_LABEL, caps.near_fit, gate_details)
    return EligibilityResult(ELIGIBLE, caps.eligible, gate_details)
