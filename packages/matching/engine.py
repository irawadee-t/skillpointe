"""
engine.py — matching engine orchestrator.

Computes a complete MatchResult for one (applicant, job) pair:

  Stage 1 — Hard eligibility gates    → eligibility_status, hard_gate_cap
  Stage 2A — Structured scoring       → weighted_structured_score, dimension_scores
  Stage 2B — Semantic score           → embedding similarity (or placeholder)
  Stage 2  — Base fit score           → hard_gate_cap * (struct*0.75 + semantic*0.25)
  Stage 3  — Policy reranking         → policy_adjusted_score
  Output   — Labels + explanation     → match_label, strengths, gaps, next_step

Guardrails (DECISIONS.md 1.12, SCORING_CONFIG.yaml):
  - No pair labeled high fit if a critical hard gate failed.
  - base_fit_score and policy_adjusted_score are ALWAYS stored separately.
  - LLM outputs are INPUTS to this module (via extracted signals), not computed here.
  - This module remains 100% deterministic.

All inputs are plain Python dicts (DB row format).  No DB I/O here.
"""
from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from . import sn_taxonomy
from .config import ScoringConfig
from .gates import (
    ELIGIBLE,
    FAIL,
    INELIGIBLE,
    NEAR_FIT,
    NEAR_FIT_LABEL,
    PASS,
    GateDetail,
    compute_eligibility,
    evaluate_credential_gate,
    evaluate_geography_gate,
    evaluate_job_family_gate,
    evaluate_min_req_gate,
    evaluate_seniority_gate,
    evaluate_timing_gate,
)
from .normalizer import TimingResult, normalize_timing
from .scorer import DimensionScore, compute_structured_score
from .text_scorer import (
    _estimate_applicant_education,
    _parse_education_required,
    compute_text_semantic_score,
)

# ---------------------------------------------------------------------------
# Semantic score: real embedding-based scoring (Phase 7) with placeholder fallback
# ---------------------------------------------------------------------------
_PLACEHOLDER_SEMANTIC_SCORE = 50.0
_PLACEHOLDER_SEMANTIC_NOTE = (
    "no embeddings available; using neutral default 50.0; "
    "run scripts/run_extraction.py to generate embeddings"
)


def _compute_semantic_score(
    a_emb: list[float], b_emb: list[float],
) -> tuple[float, str]:
    """Cosine similarity between two embedding vectors, scaled to 0–100."""
    if len(a_emb) != len(b_emb) or not a_emb:
        return 50.0, "embedding dimension mismatch; using default"
    dot = sum(x * y for x, y in zip(a_emb, b_emb))
    norm_a = math.sqrt(sum(x * x for x in a_emb))
    norm_b = math.sqrt(sum(x * x for x in b_emb))
    if norm_a == 0 or norm_b == 0:
        return 50.0, "zero-norm embedding; using default"
    sim = dot / (norm_a * norm_b)
    score = round(max(0.0, min(100.0, sim * 100.0)), 2)
    return score, f"embedding cosine similarity: {sim:.4f}"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    applicant_id: str
    job_id: str

    # Stage 1 — gates
    eligibility_status: str
    hard_gate_cap: float
    hard_gate_failures: list[dict]
    hard_gate_rationale: dict

    # Stage 2A — structured
    weighted_structured_score: float
    dimension_scores: list[DimensionScore]

    # Stage 2B — semantic (placeholder)
    semantic_score: float
    semantic_score_note: str

    # Stage 2 — base fit
    base_fit_score: float

    # Stage 3 — policy
    policy_modifiers: list[dict]
    policy_adjusted_score: float

    # Labels + explanation
    match_label: str
    top_strengths: list[str]
    top_gaps: list[str]
    required_missing_items: list[str]
    recommended_next_step: str

    # Confidence
    confidence_level: str
    requires_review: bool

    # Relaxation tier — which labeled tier admits this pair to the applicant's
    # matches surface. Visibility/grouping ONLY: tiers never change any score.
    #   'strict' | 'adjacent' | 'stretch' | 'nearby' | None (not surfaced)
    match_tier: str | None = None
    tier_reason: str | None = None

    # Geodesic home → job-city miles (None when either side lacks coords).
    # Stored for honest display and deterministic tie-breaking.
    distance_miles: float | None = None

    # Run metadata
    scoring_run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scoring_run_at: str = field(default_factory=lambda: date.today().isoformat())
    policy_version: str = "v1"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_match(
    applicant: dict[str, Any],
    job: dict[str, Any],
    employer: dict[str, Any],
    config: ScoringConfig,
    today: date | None = None,
    scoring_run_id: str | None = None,
    applicant_signals: dict[str, Any] | None = None,
    job_signals: dict[str, Any] | None = None,
    applicant_embedding: list[float] | None = None,
    job_embedding: list[float] | None = None,
) -> MatchResult:
    """
    Compute a full MatchResult for one (applicant, job) pair.

    Parameters
    ----------
    applicant : dict — DB row; must include canonical_job_family_code (joined),
                       state, region, willing_to_relocate, willing_to_travel,
                       expected_completion_date, available_from_date
    job       : dict — DB row; must include canonical_job_family_code (joined),
                       state, region, work_setting, travel_requirement,
                       pay_min, pay_max, pay_type, required_credentials
    employer  : dict — DB row; must include is_partner
    config    : ScoringConfig — loaded from active policy_configs row
    today     : override date.today() for testing
    applicant_signals : optional extracted signals from Phase 7 LLM extraction
    job_signals       : optional extracted signals from Phase 7 LLM extraction
    applicant_embedding : optional 1536-dim embedding for semantic scoring
    job_embedding       : optional 1536-dim embedding for semantic scoring
    """
    if today is None:
        today = date.today()

    run_id = scoring_run_id or str(uuid.uuid4())
    app_id = str(applicant["id"])
    job_id = str(job["id"])
    a_sig = applicant_signals or {}
    j_sig = job_signals or {}

    # ------------------------------------------------------------------
    # Stage 1 — Hard eligibility gates
    # ------------------------------------------------------------------
    timing = normalize_timing(
        applicant.get("expected_completion_date"),
        applicant.get("available_from_date"),
        today,
    )

    # Extract cert/skill lists from signals for enhanced gates
    applicant_certs = _extract_list(a_sig, "certifications_extracted", "name", "cert_name")
    applicant_skills = _extract_list(a_sig, "skills_extracted", "skill")
    job_critical_skills = _extract_critical_skills(j_sig)

    # Infer applicant years_experience if not explicitly set
    if applicant.get("years_experience") is None:
        from .text_scorer import _estimate_applicant_experience_years
        inferred_years = _estimate_applicant_experience_years(applicant)
        if inferred_years is None:
            # Default: students and recent grads have ~0 years field experience
            inferred_years = 0
        applicant = dict(applicant)  # don't mutate original
        applicant["years_experience"] = inferred_years

    # Derive education levels for credential gate
    job_text = " ".join(filter(None, [
        job.get("description_raw"),
        job.get("requirements_raw"),
        job.get("preferred_qualifications_raw"),
    ]))
    job_edu_parsed = _parse_education_required(job_text) if job_text else None
    job_min_education = job_edu_parsed["level"] if job_edu_parsed else None
    edu_or_equivalent = job_edu_parsed.get("or_equivalent", False) if job_edu_parsed else False
    applicant_education = _estimate_applicant_education(applicant)

    # Has the applicant ever stated a geography preference? Imported scholars
    # carry blanket ETL defaults (willing_to_relocate=false,
    # relocation_preference='stay_current', travel_preference='within_state',
    # no radius, no states) — that is missing data, not a stated refusal to
    # move. Only affirmative choices count as stated: a chosen radius,
    # relocation states, a willingness flag, or a willingness-bearing enum.
    geo_prefs_stated = bool(
        applicant.get("commute_radius_miles") is not None
        or applicant.get("relocation_states")
        or applicant.get("willing_to_relocate")
        or applicant.get("willing_to_travel")
        or (applicant.get("relocation_preference") or "stay_current")
        not in ("stay_current",)
        or (applicant.get("travel_preference") or "no_travel")
        not in ("no_travel", "within_state")
    )

    ge = config.gates_enabled

    def _gate(enabled: bool, name: str, evaluate):
        if not enabled:
            return GateDetail(name, "pass", "gate disabled by admin policy")
        return evaluate()

    gate_details: list[GateDetail] = [
        _gate(ge.job_family, "job_family_compatibility", lambda: evaluate_job_family_gate(
            applicant.get("canonical_job_family_code"),
            job.get("canonical_job_family_code"),
        )),
        _gate(ge.credentials, "required_credential_compatibility", lambda: evaluate_credential_gate(
            job.get("required_credentials") or [],
            applicant,
            applicant_certs=applicant_certs,
            job_min_education=job_min_education,
            applicant_education=applicant_education,
            job_required_experience_years=job.get("required_experience_years"),
            education_or_equivalent=edu_or_equivalent,
            job_entry_friendly=job.get("entry_friendly"),
        )),
        _gate(ge.timing, "readiness_timing_compatibility", lambda: evaluate_timing_gate(timing)),
        _gate(ge.geography, "geography_feasibility", lambda: evaluate_geography_gate(
            applicant.get("state"),
            applicant.get("region"),
            bool(applicant.get("willing_to_relocate")),
            bool(applicant.get("willing_to_travel")),
            job.get("state"),
            job.get("region"),
            job.get("work_setting"),
            relocation_preference=applicant.get("relocation_preference"),
            relocation_states=applicant.get("relocation_states"),
            travel_preference=applicant.get("travel_preference"),
            applicant_lat=applicant.get("lat"),
            applicant_lng=applicant.get("lng"),
            job_lat=job.get("lat"),
            job_lng=job.get("lng"),
            commute_radius_miles=applicant.get("commute_radius_miles"),
            applicant_city=applicant.get("city"),
            job_city=job.get("city"),
            geo_prefs_stated=geo_prefs_stated,
            relax_unknown_prefs=config.relax_unknown_geo_prefs,
        )),
        _gate(ge.min_requirements, "explicit_minimum_requirement_compatibility", lambda: evaluate_min_req_gate(
            applicant, job.get("description_raw"),
            applicant_skills=applicant_skills,
            job_critical_skills=job_critical_skills,
        )),
        _gate(ge.seniority, "seniority_compatibility", lambda: evaluate_seniority_gate(
            job.get("experience_level"),
            applicant.get("years_experience"),
            is_trade_school=bool(applicant.get("program_name_raw")),
            job_entry_friendly=job.get("entry_friendly"),
            job_years_required=job.get("years_experience_required")
                if job.get("years_experience_required") is not None
                else job.get("required_experience_years"),
        )),
    ]

    elig_result = compute_eligibility(gate_details, config.eligibility_caps)
    elig_status = elig_result.eligibility_status
    gate_cap = elig_result.hard_gate_cap

    # ------------------------------------------------------------------
    # Stage 2A — Structured score
    # ------------------------------------------------------------------
    w_struct_score, dim_scores = compute_structured_score(
        applicant, job, timing, config,
        applicant_signals=a_sig if a_sig else None,
        job_signals=j_sig if j_sig else None,
    )

    # ------------------------------------------------------------------
    # Stage 2B — Semantic score
    # Priority: 1) embedding cosine, 2) text-based semantic, 3) placeholder
    # ------------------------------------------------------------------
    if applicant_embedding and job_embedding:
        semantic_score, semantic_note = _compute_semantic_score(
            applicant_embedding, job_embedding
        )
    else:
        text_score, text_note = compute_text_semantic_score(applicant, job)
        if text_score != 50.0 or job.get("description_raw"):
            semantic_score = text_score
            semantic_note = text_note
        else:
            semantic_score = _PLACEHOLDER_SEMANTIC_SCORE
            semantic_note = _PLACEHOLDER_SEMANTIC_NOTE

    # ------------------------------------------------------------------
    # Stage 2 — Base fit score
    # Formula: hard_gate_cap * (struct * 0.75 + semantic * 0.25)
    # ------------------------------------------------------------------
    raw_base = (
        w_struct_score * config.structured_weight
        + semantic_score * config.semantic_weight
    )
    base_fit = round(min(100.0, max(0.0, gate_cap * raw_base)), 2)

    # ------------------------------------------------------------------
    # Stage 3 — Policy reranking
    # base_fit_score and policy_adjusted_score MUST remain separate (DECISIONS.md 1.6)
    # ------------------------------------------------------------------
    policy_mods, policy_adj = _compute_policy_adjustments(
        applicant, job, employer, elig_status, timing, config, base_fit
    )

    # ------------------------------------------------------------------
    # Labels + explanation
    # ------------------------------------------------------------------
    match_label = _compute_match_label(policy_adj, elig_status, config.match_labels)
    strengths, gaps, missing, next_step = _build_explanation(
        dim_scores, gate_details, elig_status, job
    )

    # ------------------------------------------------------------------
    # Relaxation tier — visibility/grouping only, never a score change
    # ------------------------------------------------------------------
    from .geo import distance_between
    dist = distance_between(applicant, job)
    distance_miles = round(dist, 1) if dist is not None else None

    match_tier, tier_reason = _compute_tier(
        gate_details, elig_status, config,
        distance_miles=distance_miles,
        commute_radius_miles=applicant.get("commute_radius_miles"),
    )

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------
    confidence, requires_review = _compute_confidence(gate_details, dim_scores, elig_result)

    return MatchResult(
        applicant_id=app_id,
        job_id=job_id,
        eligibility_status=elig_status,
        hard_gate_cap=gate_cap,
        hard_gate_failures=elig_result.hard_gate_failures,
        hard_gate_rationale=elig_result.hard_gate_rationale,
        weighted_structured_score=w_struct_score,
        dimension_scores=dim_scores,
        semantic_score=semantic_score,
        semantic_score_note=semantic_note,
        base_fit_score=base_fit,
        policy_modifiers=policy_mods,
        policy_adjusted_score=policy_adj,
        match_label=match_label,
        top_strengths=strengths,
        top_gaps=gaps,
        required_missing_items=missing,
        recommended_next_step=next_step,
        confidence_level=confidence,
        requires_review=requires_review,
        match_tier=match_tier,
        tier_reason=tier_reason,
        distance_miles=distance_miles,
        scoring_run_id=run_id,
        scoring_run_at=today.isoformat(),
        policy_version=config.version,
    )


# ---------------------------------------------------------------------------
# Signal extraction helpers (pure, no DB)
# ---------------------------------------------------------------------------

def _extract_list(
    signals: dict, key: str, *name_fields: str
) -> list[str] | None:
    """Extract a flat list of names from a JSONB array-of-dicts signal."""
    items = signals.get(key)
    if items is None:
        return None
    if not isinstance(items, list):
        return None
    result = []
    for item in items:
        if isinstance(item, dict):
            for nf in name_fields:
                val = item.get(nf)
                if val:
                    result.append(str(val))
                    break
    return result


def _extract_critical_skills(job_signals: dict) -> list[str] | None:
    """Extract critical/required skill names from job extraction signals."""
    req = job_signals.get("required_skills")
    if req is None:
        return None
    if not isinstance(req, list):
        return None
    result = []
    for item in req:
        if isinstance(item, dict):
            importance = item.get("importance", "important")
            if importance in ("critical", "important") and item.get("skill"):
                result.append(str(item["skill"]))
    return result


# ---------------------------------------------------------------------------
# Policy reranking helpers
# ---------------------------------------------------------------------------

def _compute_policy_adjustments(
    applicant: dict,
    job: dict,
    employer: dict,
    elig_status: str,
    timing: TimingResult,
    config: ScoringConfig,
    base_fit: float,
) -> tuple[list[dict], float]:
    """
    Apply policy modifiers from SCORING_CONFIG.yaml §policy_reranking.
    Returns (modifiers_list, policy_adjusted_score).

    DECISIONS.md 1.6: policy_adjusted_score is stored separately from base_fit_score.
    The modifiers list provides a transparent audit trail.
    """
    pm = config.policy_modifiers
    mods: list[dict] = []
    total_mod = 0.0

    # 1. Partner employer preference
    is_partner = bool(employer.get("is_partner", False))
    partner_val = pm.partner_employer if is_partner else 0.0
    mods.append({
        "policy": "partner_employer_preference",
        "value": partner_val,
        "reason": "partner employer" if is_partner else "non-partner employer",
    })
    total_mod += partner_val

    # 2. Geography preference
    geo_val = _geo_policy_modifier(applicant, job, pm)
    if geo_val != 0:
        mods.append({"policy": "geography_preference", "value": geo_val,
                     "reason": f"geography modifier +{geo_val}"})
        total_mod += geo_val

    # 3. Readiness preference
    ready_val = _readiness_policy_modifier(timing, pm)
    if ready_val != 0:
        mods.append({"policy": "readiness_preference", "value": ready_val,
                     "reason": f"readiness: {timing.readiness_label}"})
        total_mod += ready_val

    # 4. Missing critical requirement penalty (applied at policy layer for ineligible)
    if elig_status == INELIGIBLE:
        pen = pm.penalty_missing_mandatory_credential
        mods.append({"policy": "missing_critical_requirement_penalty", "value": pen,
                     "reason": "hard gate failure — critical incompatibility"})
        total_mod += pen

    # 5. Opportunity upside — pay data present + not ineligible
    if job.get("pay_min") and elig_status in (ELIGIBLE, NEAR_FIT_LABEL):
        upside = pm.opportunity_upside
        mods.append({"policy": "opportunity_upside", "value": upside,
                     "reason": "pay data present, eligible or near-fit"})
        total_mod += upside

    policy_adj = round(max(0.0, min(100.0, base_fit + total_mod)), 2)
    return mods, policy_adj


def _geo_policy_modifier(applicant: dict, job: dict, pm) -> float:
    ws = (job.get("work_setting") or "").lower()
    if ws == "remote":
        return pm.geo_local

    # Distance-aware: inside the applicant's commute radius counts as local.
    from .geo import distance_between, effective_radius_miles
    dist = distance_between(applicant, job)
    if dist is not None:
        if dist <= effective_radius_miles(applicant.get("commute_radius_miles")):
            return pm.geo_local

    app_state = applicant.get("state")
    job_state = job.get("state")
    app_region = applicant.get("region")
    job_region = job.get("region")
    reloc_states = applicant.get("relocation_states") or []
    r_pref = applicant.get("relocation_preference") or (
        "anywhere" if applicant.get("willing_to_relocate") else "stay_current"
    )
    t_pref = applicant.get("travel_preference") or (
        "regional" if applicant.get("willing_to_travel") else "no_travel"
    )

    if app_state and job_state and app_state.upper() == job_state.upper():
        return pm.geo_local
    if reloc_states and job_state and job_state.upper() in {s.upper() for s in reloc_states}:
        return pm.geo_local
    if app_region and job_region and app_region.lower() == job_region.lower():
        if r_pref in ("anywhere", "within_region") or t_pref in ("regional", "within_region", "nationwide", "anywhere"):
            return pm.geo_same_state
        return 0.0  # same region but not willing — no bonus
    if r_pref == "anywhere":
        return pm.geo_relocation_willing
    return 0.0


def _readiness_policy_modifier(timing: TimingResult, pm) -> float:
    if timing.readiness_label == "available_now":
        return pm.readiness_ready_now
    if timing.readiness_label == "near_completion":
        return pm.readiness_near_completion
    return 0.0


# ---------------------------------------------------------------------------
# Match label + explanation helpers
# ---------------------------------------------------------------------------

def _compute_match_label(score: float, elig_status: str, labels=None) -> str:
    """Bucket policy_adjusted_score into a match_label.

    Thresholds come from config (admin-calibratable against the live score
    distribution). Eligibility caps labels: an ineligible pair is always
    low_fit, and a near-fit can never read "strong fit" — a pair with an open
    gate gap must not display the top label (DECISIONS.md 1.12 in spirit).
    """
    from .config import MatchLabelConfig
    lab = labels or MatchLabelConfig()
    if elig_status == INELIGIBLE:
        return "low_fit"
    if score >= lab.strong_fit_min:
        label = "strong_fit"
    elif score >= lab.good_fit_min:
        label = "good_fit"
    elif score >= lab.moderate_fit_min:
        label = "moderate_fit"
    else:
        label = "low_fit"
    if elig_status == NEAR_FIT_LABEL and label == "strong_fit":
        label = "good_fit"
    return label


def _compute_tier(
    gate_details: list[GateDetail],
    elig_status: str,
    config: ScoringConfig,
    distance_miles: float | None = None,
    commute_radius_miles: float | None = None,
) -> tuple[str | None, str | None]:
    """Assign the labeled relaxation tier that admits this pair to the
    applicant's matches surface (progressive relaxation for sparse markets).

    Tier semantics — each match carries WHICH relaxation admitted it so the
    UI can group honestly; a tier NEVER changes any score:
      strict   — eligible: every hard gate passed
      adjacent — near-fit whose trade is direct/adjacent AND geography passed
      stretch  — other near-fits (admitted by a geography/timing/credential
                 stretch, e.g. beyond-radius with unknown relocation prefs)
      nearby   — "Near you, different trade": geography PASSED but the trade
                 is unrelated; every other gate is clean. Ineligible for
                 ranking purposes (score stays capped) but surfaceable when
                 stricter tiers leave the applicant with too few results.
      None     — not surfaced by any tier
    """
    relax = config.relaxation
    if elig_status == ELIGIBLE:
        return "strict", "Meets all requirements"

    by_name = {g.gate_name: g for g in gate_details}
    fam = by_name.get("job_family_compatibility")
    geo = by_name.get("geography_feasibility")
    fails = [g for g in gate_details if g.result == FAIL]

    if elig_status == NEAR_FIT_LABEL:
        if not relax.enabled or not relax.tier_adjacent:
            return None, None
        fam_ok = fam is None or fam.result in (PASS, NEAR_FIT)
        geo_pass = geo is None or geo.result == PASS
        # "near you" wording only with VERIFIED proximity — a geography PASS
        # for "location not assessed" or remote must not read as nearby.
        from .geo import effective_radius_miles
        verified_near = (
            distance_miles is not None
            and distance_miles <= max(
                effective_radius_miles(commute_radius_miles),
                float(relax.nearby_max_miles),
            )
        )
        if fam_ok and geo_pass:
            if fam is not None and fam.result == NEAR_FIT:
                # "Related trade" is a factual claim — only make it when BOTH
                # family codes are known and adjacent. An unknown program is
                # missing data: say that, don't assert a relationship.
                if "unknown" in fam.reason:
                    return "adjacent", (
                        "Near you. Add your trade to confirm fit"
                        if verified_near else "Add your trade to confirm fit"
                    )
                return "adjacent", (
                    "Related trade, near you" if verified_near else "Related trade"
                )
            return "adjacent", (
                "Close match near you" if verified_near else "Close match"
            )
        return "stretch", "Worth a look, one gap to close"

    # Ineligible: the only surfaceable case is "verifiably near, trade
    # doesn't match" — the user's "just geography based matches" tier.
    # VERIFIED proximity is required: a known geodesic distance within
    # max(applicant's radius, relaxation.nearby_max_miles). A geography-gate
    # PASS alone is NOT enough — "location not assessed" (missing job state)
    # and remote jobs must never be labeled "Near you".
    if not relax.enabled or not relax.tier_nearby:
        return None, None
    from .geo import effective_radius_miles
    nearby_cap = max(
        effective_radius_miles(commute_radius_miles), float(relax.nearby_max_miles)
    )
    if (
        fam is not None and fam.result == FAIL
        and geo is not None and geo.result in (PASS, NEAR_FIT)
        and all(g.gate_name == "job_family_compatibility" for g in fails)
        and distance_miles is not None
        and distance_miles <= nearby_cap
    ):
        return "nearby", "Near you, different trade"
    return None, None


_DIMENSION_LABELS = {
    "trade_program_alignment": "Your trade matches this role",
    "geography_alignment": "Location works for you",
    "credential_readiness": "You have the credentials",
    "timing_readiness": "Timing is right",
    "experience_internship_alignment": "Relevant experience",
    "industry_alignment": "Industry fit",
    # Note: we never collect pay *expectations* — this label is only a
    # fallback; _strength_text surfaces the job's real pay figures instead.
    "compensation_alignment": "Competitive pay listed",
    "work_style_signal_alignment": "Work style fits",
    "employer_soft_pref_alignment": "Matches employer preferences",
}

_DIMENSION_GAP_LABELS = {
    "trade_program_alignment": "Different trade background",
    "geography_alignment": "Location may be a challenge",
    "credential_readiness": "Credentials gap",
    "timing_readiness": "Timing mismatch",
    "experience_internship_alignment": "More experience needed",
    "industry_alignment": "Different industry",
    "compensation_alignment": "Pay may not align",
    "work_style_signal_alignment": "Work style differs",
    "employer_soft_pref_alignment": "Employer preference gap",
}

_GATE_LABELS = {
    "job_family_compatibility": "Trade alignment",
    "required_credential_compatibility": "Required credentials",
    "readiness_timing_compatibility": "Availability timing",
    "geography_feasibility": "Location",
    "explicit_minimum_requirement_compatibility": "Job requirements",
    "seniority_compatibility": "Experience level",
}


_EDU_FRIENDLY = {
    "high_school": "high school diploma",
    "trade_cert": "trade certificate",
    "associates": "associate's degree",
    "bachelors": "bachelor's degree",
    "military": "military training",
}


def _friendly_family(code: str) -> str:
    """'hvac_r' → 'HVAC/R', 'nursing' → 'nursing' — readable trade names.

    New taxonomy codes render their display name with any parenthetical
    dropped and non-acronym words lowercased, so the sentence "this is a
    nursing role" reads naturally while "HVAC/R" and "CAD/CAM" keep caps.
    """
    special = {"hvac_r": "HVAC/R", "hvac": "HVAC", "cdl": "CDL", "it": "IT"}
    if code.lower() in special:
        return special[code.lower()]
    resolved = sn_taxonomy.resolve_field_code(code)
    if resolved:
        name = re.sub(r"\s*\(.*\)$", "", sn_taxonomy.FIELDS[resolved]["name"]).strip()
        words = [
            w if (w.isupper() or any(ch.isupper() for ch in w[1:])) else w.lower()
            for w in name.split()
        ]
        return " ".join(words)
    return code.replace("_", " ")


def _humanize_gate_reason(gate_name: str, reason: str) -> str:
    """Convert technical gate reason to technician-friendly language."""
    if gate_name == "job_family_compatibility":
        m = re.match(r"unrelated families: applicant=(\S+), job=(\S+)", reason)
        if m:
            return (
                f"this is a {_friendly_family(m.group(2))} role, "
                f"your training is in {_friendly_family(m.group(1))}"
            )
        return reason[:120]

    if gate_name == "required_credential_compatibility":
        parts = []
        for segment in reason.split(";"):
            segment = segment.strip()
            m = re.match(r"education mismatch: job requires (\w+), applicant has (\w+)", segment)
            if m:
                job_edu = _EDU_FRIENDLY.get(m.group(1), m.group(1))
                app_edu = _EDU_FRIENDLY.get(m.group(2), m.group(2))
                parts.append(f"this job needs a {job_edu} (you have a {app_edu})")
                continue
            m = re.match(r"education.*?close to (\w+)", segment)
            if m:
                job_edu = _EDU_FRIENDLY.get(m.group(1), m.group(1))
                parts.append(f"job prefers a {job_edu}")
                continue
            m = re.match(r"requires \[(.+?)\].*not yet verified", segment)
            if m:
                parts.append(f"requires {m.group(1)}")
                continue
            m = re.match(r"job (?:requires|needs) (\d+)\+? ?y(?:ea)?rs? experience.*(?:significant|substantial|field)", segment)
            if m:
                parts.append(f"needs {m.group(1)}+ years experience")
                continue
            m = re.match(r"job needs (\d+).*new grad", segment)
            if m:
                parts.append(f"prefers {m.group(1)}+ years experience")
                continue
            m = re.match(r"job prefers (\d+).*trade", segment)
            if m:
                continue  # 1 year + trade training = fine, don't show as gap
            if segment:
                parts.append(segment[:80])
        return "; ".join(parts) if parts else reason[:120]

    if gate_name == "seniority_compatibility":
        if "senior" in reason.lower():
            return "senior-level role, needs significant experience"
        if "management" in reason.lower():
            return "management role, needs leadership experience"
        return reason[:80]

    if gate_name == "geography_feasibility":
        # Distance-based reasons ("~62 mi away, beyond your 25 mi radius…")
        # are already written for the applicant — keep them intact.
        if " mi " in reason or "radius" in reason:
            return reason[:160]
        if "mismatch" in reason:
            return "location doesn't match your preferences"
        return reason[:80]

    return reason[:120]


def _strength_text(d: DimensionScore) -> str | None:
    """Grounded strength wording for one high-scoring dimension.

    Every sentence must be provable from the dimension's own rationale —
    never a claim about data we don't hold:
      - pay: we never collect pay *expectations*, so surface the job's real
        pay figures ("Competitive hourly pay: $22–$28/hr"), not
        "pay matches expectations";
      - credentials: a high score because the job asks for nothing extra must
        not read "you have the credentials";
      - timing: say the real availability ("Available in ~4 months") instead
        of a blanket "timing is right";
      - soft skills assumed from trade training (empty profile) are not a
        verified strength — suppressed entirely.
    Returns None when the dimension has no honest strength sentence.
    """
    r = d.rationale
    if d.dimension == "geography_alignment":
        # Geography is first-class: surface the real distance when we have
        # it ("~18 mi from Austin, inside your 25 mi radius").
        if " mi " in r or "radius" in r:
            return r[0].upper() + r[1:]
        return _DIMENSION_LABELS["geography_alignment"]
    if d.dimension == "compensation_alignment":
        if r.startswith("competitive"):
            return r[0].upper() + r[1:]
        return None
    if d.dimension == "credential_readiness":
        if r.startswith("no explicit credential"):
            return "No extra credentials required"
        return _DIMENSION_LABELS["credential_readiness"]
    if d.dimension == "timing_readiness":
        m = re.search(r"~(\d+) month", r)
        months = int(m.group(1)) if m else None
        unit = "month" if months == 1 else "months"
        if r.startswith("applicant is available now"):
            return "Available now"
        if r.startswith("near completion") and m:
            return f"Finishing your program in ~{months} {unit}"
        if r.startswith("in progress") and m:
            return f"Available in ~{months} {unit}"
        return _DIMENSION_LABELS["timing_readiness"]
    if d.dimension == "employer_soft_pref_alignment":
        if r.startswith("likely soft-skill fit"):
            return None
        return _DIMENSION_LABELS["employer_soft_pref_alignment"]
    return _DIMENSION_LABELS.get(d.dimension, d.dimension.replace("_", " "))


def _build_explanation(
    dim_scores: list[DimensionScore],
    gate_details: list[GateDetail],
    elig_status: str,
    job: dict,
) -> tuple[list[str], list[str], list[str], str]:
    """
    Build human-readable explanation lists from scoring outputs.
    Returns (top_strengths, top_gaps, required_missing_items, recommended_next_step).

    Language is written for trade school students — clear, encouraging, actionable.
    """
    strengths: list[str] = []
    gaps: list[str] = []
    missing: list[str] = []

    sorted_dims = sorted(dim_scores, key=lambda d: d.raw_score, reverse=True)
    for d in sorted_dims:
        if d.raw_score >= 70 and not d.null_handling_applied and len(strengths) < 4:
            text = _strength_text(d)
            if text:
                strengths.append(text)

    for g in gate_details:
        label = _GATE_LABELS.get(g.gate_name, g.gate_name.replace("_", " "))
        if g.result == "fail":
            friendly = _humanize_gate_reason(g.gate_name, g.reason)
            gaps.append(f"{label}: {friendly}")
            if g.severity == "critical":
                missing.append(friendly)
        elif g.result == "near_fit" and g.gate_name == "required_credential_compatibility":
            if ("education" in g.reason or "credential" in g.reason
                    or "experience" in g.reason or "certification" in g.reason):
                friendly = _humanize_gate_reason(g.gate_name, g.reason)
                gaps.append(f"{label}: {friendly}")
        elif g.result == "near_fit" and g.gate_name == "geography_feasibility":
            # Distance-worded near-fits ("just beyond your 25 mi radius")
            # are actionable — show them as a gap so the radius trade-off
            # is visible in real terms.
            if " mi " in g.reason or "radius" in g.reason:
                gaps.append(f"{label}: {g.reason[:160]}")

    has_trade_gate_gap = any(g.startswith("Trade alignment") for g in gaps)
    for d in sorted_dims:
        if d.raw_score < 50 and not d.null_handling_applied and len(gaps) < 5:
            if d.dimension == "geography_alignment" and any(
                g.startswith("Location") for g in gaps
            ):
                continue  # distance-worded gate gap already covers it
            if (
                d.dimension in ("trade_program_alignment", "industry_alignment")
                and has_trade_gate_gap
            ):
                # The trade-alignment gate gap already states the mismatch in
                # full ("this is a manufacturing role, your training is in
                # nursing"); don't restate it as two more generic chips.
                continue
            label = _DIMENSION_GAP_LABELS.get(d.dimension, d.dimension.replace("_", " "))
            gaps.append(label)

    if elig_status == ELIGIBLE and not gaps:
        next_step = "You're a strong match. Apply now."
    elif elig_status == ELIGIBLE:
        next_step = "Good fit. Review the description and apply."
    elif elig_status == NEAR_FIT_LABEL:
        # Bridgeable gaps get the ACTION, not just the observation: a missing
        # certification is a course away, and a start-date gap is a message
        # away. The door stays open and the path is stated.
        joined_gaps = " | ".join(gaps)
        if "attainable" in joined_gaps:
            m = re.search(r"missing attainable[^\[]*\[([^\]]+)\]", joined_gaps)
            cert = m.group(1).split(",")[0].strip() if m else "the listed certification"
            next_step = (
                f"You can still earn {cert}. Check the training options on "
                "this page, then apply."
            )
        elif "apply and message the employer" in joined_gaps:
            next_step = (
                "Your finish date is close to their start. Apply, then message "
                "the employer about timing."
            )
        elif gaps:
            first_gap = gaps[0].split(":")[0] if ":" in gaps[0] else gaps[0]
            next_step = f"Worth a look: {first_gap.lower().strip()}"
        else:
            next_step = "Close match. Check the requirements."
    else:
        if missing:
            first = missing[0]
            if first.startswith("~") or "radius" in first:
                # Geography failure — say what to change, not a raw distance.
                next_step = (
                    "Outside your commute area right now. Widen your radius "
                    "or update relocation settings if you'd travel."
                )
            elif "your training is in" in first:
                next_step = "Different trade background. Keep building your skills."
            else:
                # Lowercase the leading word only when it isn't an acronym
                # ("Look into: requires OSHA 10", not "requires osha 10").
                lead = (
                    first[0].lower() + first[1:]
                    if len(first) > 1 and first[1].islower()
                    else first
                )
                next_step = f"Look into: {lead}"
        else:
            next_step = "Different trade background. Keep building your skills."

    return strengths[:5], gaps[:5], missing[:5], next_step


def _compute_confidence(
    gate_details: list[GateDetail],
    dim_scores: list[DimensionScore],
    elig_result,
) -> tuple[str, bool]:
    """
    Compute confidence_level ('high', 'medium', 'low') and requires_review flag.

    Confidence is lower when:
    - many dimensions used null-handling defaults (sparse data)
    - gates had needs_review = True
    """
    null_count = sum(1 for d in dim_scores if d.null_handling_applied)
    review_gates = sum(1 for g in gate_details if g.needs_review)

    requires_review = elig_result.requires_review or review_gates >= 2

    if null_count >= 5 or review_gates >= 3:
        return "low", True
    if null_count >= 3 or review_gates >= 2:
        return "medium", requires_review
    return "high", requires_review
