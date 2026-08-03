"""
config.py — scoring configuration loader for SkillPointe Match.

Priority order:
  1. If a yaml_path is supplied, load from that file.
  2. Default: repo-root SCORING_CONFIG.yaml
  3. Fallback: built-in hardcoded defaults (for unit tests with no file access)

The ScoringConfig dataclass is the canonical in-memory representation
used by normalizer, gates, scorer, and engine.  All other modules accept
ScoringConfig as a parameter so they never read the filesystem directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Path from packages/matching/config.py → repo root / SCORING_CONFIG.yaml
_CONFIG_PATH = Path(__file__).parent.parent.parent / "SCORING_CONFIG.yaml"


# ---------------------------------------------------------------------------
# Sub-config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EligibilityCapConfig:
    eligible: float = 1.0
    near_fit: float = 0.75
    ineligible: float = 0.35


@dataclass
class StructuredWeights:
    trade_program_alignment: float = 25.0
    geography_alignment: float = 20.0
    credential_readiness: float = 15.0
    timing_readiness: float = 10.0
    experience_internship_alignment: float = 10.0
    industry_alignment: float = 5.0
    compensation_alignment: float = 5.0
    work_style_signal_alignment: float = 5.0
    employer_soft_pref_alignment: float = 5.0


@dataclass
class NullHandlingConfig:
    compensation_alignment_unknown: float = 70.0
    employer_soft_pref_alignment_unknown: float = 50.0
    work_style_signal_alignment_unknown: float = 50.0
    geography_partially_known: float = 50.0
    geography_fully_unknown: float = 35.0
    credentials_unknown_nonrequired: float = 50.0
    experience_unknown: float = 50.0


@dataclass
class MatchLabelConfig:
    """policy_adjusted_score thresholds for the match_label buckets.

    Calibrated against the real score distribution (eligible pairs land at
    ~65–100 after policy modifiers; near-fits cap out around ~62) and
    admin-configurable via policy_configs. Eligibility still caps labels:
    ineligible pairs are always low_fit regardless of score.
    """
    strong_fit_min: float = 80.0
    good_fit_min: float = 60.0
    moderate_fit_min: float = 40.0


@dataclass
class RelaxationConfig:
    """Progressive relaxation (tiered surfacing) for sparse markets.

    When an applicant's strict matches fall below ``min_results``, the
    serving layer expands through explicit, labeled tiers instead of showing
    a blank page. Tiers change VISIBILITY only — never any score.
    """
    enabled: bool = True
    min_results: int = 5            # floor before lower tiers unlock
    tier_adjacent: bool = True      # near-fit, adjacent trade, geography works
    tier_nearby: bool = True        # verified-nearby, unrelated trade
    # The nearby tier requires VERIFIED proximity: a known geodesic distance
    # within max(applicant's radius, this cap). A geography-gate PASS alone
    # is not enough — "location not assessed" and remote jobs must never be
    # labeled "Near you".
    nearby_max_miles: float = 75.0


@dataclass
class GatesEnabledConfig:
    """Admin gate toggles. A disabled gate is skipped (treated as PASS)."""
    job_family: bool = True
    credentials: bool = True
    timing: bool = True
    geography: bool = True
    min_requirements: bool = True
    seniority: bool = True


@dataclass
class PolicyModifiers:
    partner_employer: float = 5.0
    funded_direct: float = 6.0
    funded_adjacent: float = 3.0
    geo_local: float = 6.0
    geo_same_state: float = 4.0
    geo_relocation_willing: float = 1.0
    geo_travel_willing: float = 1.0
    readiness_ready_now: float = 5.0
    readiness_near_completion: float = 3.0
    opportunity_upside: float = 2.0
    penalty_missing_mandatory_credential: float = -12.0
    penalty_missing_important_skill: float = -6.0
    penalty_missing_minor: float = -2.0
    max_partner_override_gap: float = 12.0


@dataclass
class ScoringConfig:
    version: str = "v1"
    eligibility_caps: EligibilityCapConfig = field(default_factory=EligibilityCapConfig)
    structured_weights: StructuredWeights = field(default_factory=StructuredWeights)
    null_handling: NullHandlingConfig = field(default_factory=NullHandlingConfig)
    policy_modifiers: PolicyModifiers = field(default_factory=PolicyModifiers)
    match_labels: MatchLabelConfig = field(default_factory=MatchLabelConfig)
    relaxation: RelaxationConfig = field(default_factory=RelaxationConfig)
    gates_enabled: GatesEnabledConfig = field(default_factory=GatesEnabledConfig)
    structured_weight: float = 0.75   # base_fit formula weight for structured score
    semantic_weight: float = 0.25     # base_fit formula weight for semantic score
    # Sparse-data geography rule: when the applicant has never stated ANY
    # geography preference (no chosen radius, no relocation states, not
    # willing-to-relocate), a beyond-radius job is a NEAR_FIT ("potentially
    # eligible — missing data"), not a hard FAIL. An explicitly chosen radius
    # or stay_current-with-radius keeps the hard FAIL. Mirrors the
    # clinical-trial "indeterminate" pattern: unknown never silently fails
    # a hard gate.
    relax_unknown_geo_prefs: bool = True


# ---------------------------------------------------------------------------
# Weight helpers + validation
# ---------------------------------------------------------------------------

WEIGHT_FIELDS = (
    "trade_program_alignment", "geography_alignment", "credential_readiness",
    "timing_readiness", "experience_internship_alignment", "industry_alignment",
    "compensation_alignment", "work_style_signal_alignment",
    "employer_soft_pref_alignment",
)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Scale a weights dict so the total is exactly 100 (2-dp rounding, the
    residual applied to the largest weight so the sum is exact)."""
    vals = {k: max(0.0, float(weights.get(k, 0.0))) for k in WEIGHT_FIELDS}
    total = sum(vals.values())
    if total <= 0:
        return {k: getattr(StructuredWeights(), k) for k in WEIGHT_FIELDS}
    scaled = {k: round(v * 100.0 / total, 2) for k, v in vals.items()}
    residual = round(100.0 - sum(scaled.values()), 2)
    if residual:
        top = max(scaled, key=lambda k: scaled[k])
        scaled[top] = round(scaled[top] + residual, 2)
    return scaled


def validate_config_dict(raw: dict[str, Any]) -> list[str]:
    """Validate an admin-supplied config dict (SCORING_CONFIG-shaped).

    Returns a list of human-readable errors; empty list = valid.
    """
    errors: list[str] = []

    weights = (raw.get("structured_score") or {}).get("weights") or {}
    if weights:
        unknown = set(weights) - set(WEIGHT_FIELDS)
        if unknown:
            errors.append(f"Unknown weight fields: {sorted(unknown)}")
        try:
            total = sum(float(weights.get(k, 0)) for k in WEIGHT_FIELDS)
        except (TypeError, ValueError):
            errors.append("Weights must be numbers")
            total = None
        if total is not None:
            if any(float(weights.get(k, 0)) < 0 for k in WEIGHT_FIELDS):
                errors.append("Weights must be >= 0")
            if abs(total - 100.0) > 0.5:
                errors.append(
                    f"Dimension weights must sum to 100 (got {total:g}) — "
                    "use normalize to scale them"
                )

    labels = raw.get("match_labels") or {}
    if labels:
        try:
            strong = float(labels.get("strong_fit_min", 80))
            good = float(labels.get("good_fit_min", 60))
            moderate = float(labels.get("moderate_fit_min", 40))
        except (TypeError, ValueError):
            errors.append("Label thresholds must be numbers")
        else:
            if not (0 <= moderate < good < strong <= 100):
                errors.append(
                    "Label thresholds must satisfy 0 <= moderate < good < strong <= 100"
                )

    caps = (raw.get("eligibility") or {}).get("labels") or {}
    if caps:
        try:
            e = float((caps.get("eligible") or {}).get("hard_gate_cap", 1.0))
            n = float((caps.get("near_fit") or {}).get("hard_gate_cap", 0.75))
            i = float((caps.get("ineligible") or {}).get("hard_gate_cap", 0.35))
        except (TypeError, ValueError):
            errors.append("Eligibility caps must be numbers")
        else:
            if not (0 <= i <= n <= e <= 1):
                errors.append(
                    "Eligibility caps must satisfy 0 <= ineligible <= near_fit <= eligible <= 1"
                )

    relax = raw.get("relaxation") or {}
    if relax:
        mr = relax.get("min_results", 5)
        if not isinstance(mr, (int, float)) or not (0 <= int(mr) <= 50):
            errors.append("relaxation.min_results must be between 0 and 50")
        nm = relax.get("nearby_max_miles", 75)
        if not isinstance(nm, (int, float)) or not (0 < float(nm) <= 300):
            errors.append("relaxation.nearby_max_miles must be between 1 and 300")

    blend = (raw.get("base_fit") or {}).get("weights") or {}
    if blend:
        try:
            s = float(blend.get("structured", 0.75))
            m = float(blend.get("semantic", 0.25))
        except (TypeError, ValueError):
            errors.append("base_fit weights must be numbers")
        else:
            if abs((s + m) - 1.0) > 0.01 or s < 0 or m < 0:
                errors.append(
                    "base_fit structured + semantic weights must be >= 0 and sum to 1"
                )

    return errors


def config_to_dict(cfg: ScoringConfig) -> dict[str, Any]:
    """Serialize a ScoringConfig back to the SCORING_CONFIG-shaped dict that
    policy_configs.config stores and ``_from_yaml`` parses (round-trippable)."""
    w = cfg.structured_weights
    pm = cfg.policy_modifiers
    return {
        "version": cfg.version,
        "eligibility": {
            "labels": {
                "eligible": {"hard_gate_cap": cfg.eligibility_caps.eligible},
                "near_fit": {"hard_gate_cap": cfg.eligibility_caps.near_fit},
                "ineligible": {"hard_gate_cap": cfg.eligibility_caps.ineligible},
            },
        },
        "structured_score": {
            "weights": {k: getattr(w, k) for k in WEIGHT_FIELDS},
        },
        "base_fit": {
            "weights": {
                "structured": cfg.structured_weight,
                "semantic": cfg.semantic_weight,
            },
        },
        "match_labels": {
            "strong_fit_min": cfg.match_labels.strong_fit_min,
            "good_fit_min": cfg.match_labels.good_fit_min,
            "moderate_fit_min": cfg.match_labels.moderate_fit_min,
        },
        "relaxation": {
            "enabled": cfg.relaxation.enabled,
            "min_results": cfg.relaxation.min_results,
            "nearby_max_miles": cfg.relaxation.nearby_max_miles,
            "tiers": {
                "adjacent": cfg.relaxation.tier_adjacent,
                "nearby_other_trade": cfg.relaxation.tier_nearby,
            },
        },
        "gates": {
            "job_family_compatibility": cfg.gates_enabled.job_family,
            "required_credential_compatibility": cfg.gates_enabled.credentials,
            "readiness_timing_compatibility": cfg.gates_enabled.timing,
            "geography_feasibility": cfg.gates_enabled.geography,
            "explicit_minimum_requirement_compatibility": cfg.gates_enabled.min_requirements,
            "seniority_compatibility": cfg.gates_enabled.seniority,
        },
        "geography_relaxation": {
            "relax_unknown_prefs": cfg.relax_unknown_geo_prefs,
        },
        "null_handling": {
            "defaults": {
                "compensation_alignment_unknown": cfg.null_handling.compensation_alignment_unknown,
                "employer_soft_pref_alignment_unknown": cfg.null_handling.employer_soft_pref_alignment_unknown,
                "work_style_signal_alignment_unknown": cfg.null_handling.work_style_signal_alignment_unknown,
                "geography_partially_known": cfg.null_handling.geography_partially_known,
                "geography_fully_unknown": cfg.null_handling.geography_fully_unknown,
                "credentials_unknown_nonrequired": cfg.null_handling.credentials_unknown_nonrequired,
                "experience_unknown": cfg.null_handling.experience_unknown,
            },
        },
        "policy_reranking": {
            "policies": {
                "partner_employer_preference": {
                    "modifiers": {"partner_employer": pm.partner_employer, "non_partner": 0},
                    "constraints": {"max_override_gap": pm.max_partner_override_gap},
                },
                "funded_training_pathway_alignment": {
                    "modifiers": {"direct_alignment": pm.funded_direct, "adjacent_alignment": pm.funded_adjacent, "unrelated": 0},
                },
                "geography_preference": {
                    "modifiers": {
                        "local_feasible": pm.geo_local,
                        "same_state_or_regional": pm.geo_same_state,
                        "relocation_required_and_willing": pm.geo_relocation_willing,
                        "travel_heavy_and_willing": pm.geo_travel_willing,
                        "uncertain": 0, "infeasible": 0,
                    },
                },
                "readiness_preference": {
                    "modifiers": {
                        "ready_now_or_timing_aligned": pm.readiness_ready_now,
                        "near_completion": pm.readiness_near_completion,
                        "significant_wait": 0,
                    },
                },
                "opportunity_upside": {
                    "modifiers": {"meaningful_upside_and_near_fit_or_better": pm.opportunity_upside, "otherwise": 0},
                },
                "missing_critical_requirement_penalty": {
                    "modifiers": {
                        "missing_mandatory_credential": pm.penalty_missing_mandatory_credential,
                        "missing_important_nonmandatory_skill_cluster": pm.penalty_missing_important_skill,
                        "missing_minor_requirements_only": pm.penalty_missing_minor,
                    },
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config(yaml_path: str | Path | None = None) -> ScoringConfig:
    """
    Load ScoringConfig from YAML.  Falls back to built-in defaults if
    the file is missing or unreadable.
    """
    path = Path(yaml_path) if yaml_path else _CONFIG_PATH
    if path.exists():
        try:
            import yaml  # type: ignore
            with open(path) as f:
                raw = yaml.safe_load(f)
            return _from_yaml(raw)
        except Exception:
            # LOUD failure: a malformed SCORING_CONFIG.yaml silently rescoring
            # the whole platform on hardcoded defaults is an integrity incident,
            # not a fallback. Keep serving (defaults) but make it unmissable.
            import logging
            logging.getLogger(__name__).error(
                "SCORING CONFIG FAILED TO LOAD from %s — scoring is running on "
                "HARDCODED DEFAULTS. Fix the YAML and recompute matches.",
                path, exc_info=True,
            )
    return ScoringConfig()


def _from_yaml(raw: dict[str, Any]) -> ScoringConfig:
    cfg = ScoringConfig()
    cfg.version = raw.get("version", "v1")

    # Eligibility caps
    elig = raw.get("eligibility", {}).get("labels", {})
    if elig:
        cfg.eligibility_caps = EligibilityCapConfig(
            eligible=elig.get("eligible", {}).get("hard_gate_cap", 1.0),
            near_fit=elig.get("near_fit", {}).get("hard_gate_cap", 0.75),
            ineligible=elig.get("ineligible", {}).get("hard_gate_cap", 0.35),
        )

    # Structured weights (normalized to sum 100 so a hand-edited config can
    # never silently deflate/inflate every base_fit score)
    weights = raw.get("structured_score", {}).get("weights", {})
    if weights:
        weights = normalize_weights(weights)
        cfg.structured_weights = StructuredWeights(
            trade_program_alignment=weights.get("trade_program_alignment", 25),
            geography_alignment=weights.get("geography_alignment", 20),
            credential_readiness=weights.get("credential_readiness", 15),
            timing_readiness=weights.get("timing_readiness", 10),
            experience_internship_alignment=weights.get("experience_internship_alignment", 10),
            industry_alignment=weights.get("industry_alignment", 5),
            compensation_alignment=weights.get("compensation_alignment", 5),
            work_style_signal_alignment=weights.get("work_style_signal_alignment", 5),
            employer_soft_pref_alignment=weights.get("employer_soft_pref_alignment", 5),
        )

    # Null handling defaults
    null = raw.get("null_handling", {}).get("defaults", {})
    if null:
        cfg.null_handling = NullHandlingConfig(
            compensation_alignment_unknown=null.get("compensation_alignment_unknown", 70),
            employer_soft_pref_alignment_unknown=null.get("employer_soft_pref_alignment_unknown", 50),
            work_style_signal_alignment_unknown=null.get("work_style_signal_alignment_unknown", 50),
            geography_partially_known=null.get("geography_partially_known", 50),
            geography_fully_unknown=null.get("geography_fully_unknown", 35),
            credentials_unknown_nonrequired=null.get("credentials_unknown_nonrequired", 50),
            experience_unknown=null.get("experience_unknown", 50),
        )

    # Policy modifiers
    policy = raw.get("policy_reranking", {}).get("policies", {})
    if policy:
        pm = PolicyModifiers()

        partner = policy.get("partner_employer_preference", {})
        pm.partner_employer = partner.get("modifiers", {}).get("partner_employer", 5)
        pm.max_partner_override_gap = partner.get("constraints", {}).get("max_override_gap", 12)

        funded = policy.get("funded_training_pathway_alignment", {}).get("modifiers", {})
        pm.funded_direct = funded.get("direct_alignment", 6)
        pm.funded_adjacent = funded.get("adjacent_alignment", 3)

        geo = policy.get("geography_preference", {}).get("modifiers", {})
        pm.geo_local = geo.get("local_feasible", 6)
        pm.geo_same_state = geo.get("same_state_or_regional", 4)
        pm.geo_relocation_willing = geo.get("relocation_required_and_willing", 1)
        pm.geo_travel_willing = geo.get("travel_heavy_and_willing", 1)

        ready = policy.get("readiness_preference", {}).get("modifiers", {})
        pm.readiness_ready_now = ready.get("ready_now_or_timing_aligned", 5)
        pm.readiness_near_completion = ready.get("near_completion", 3)

        upside = policy.get("opportunity_upside", {}).get("modifiers", {})
        pm.opportunity_upside = upside.get("meaningful_upside_and_near_fit_or_better", 2)

        penalty = policy.get("missing_critical_requirement_penalty", {}).get("modifiers", {})
        pm.penalty_missing_mandatory_credential = penalty.get("missing_mandatory_credential", -12)
        pm.penalty_missing_important_skill = penalty.get("missing_important_nonmandatory_skill_cluster", -6)
        pm.penalty_missing_minor = penalty.get("missing_minor_requirements_only", -2)

        cfg.policy_modifiers = pm

    # Match label thresholds
    labels = raw.get("match_labels", {})
    if labels:
        cfg.match_labels = MatchLabelConfig(
            strong_fit_min=float(labels.get("strong_fit_min", 80)),
            good_fit_min=float(labels.get("good_fit_min", 60)),
            moderate_fit_min=float(labels.get("moderate_fit_min", 40)),
        )

    # Relaxation tiers
    relax = raw.get("relaxation", {})
    if relax:
        tiers = relax.get("tiers", {}) or {}
        cfg.relaxation = RelaxationConfig(
            enabled=bool(relax.get("enabled", True)),
            min_results=int(relax.get("min_results", 5)),
            tier_adjacent=bool(tiers.get("adjacent", True)),
            tier_nearby=bool(tiers.get("nearby_other_trade", True)),
            nearby_max_miles=float(relax.get("nearby_max_miles", 75.0)),
        )

    # Gate toggles
    gates = raw.get("gates", {})
    if gates:
        cfg.gates_enabled = GatesEnabledConfig(
            job_family=bool(gates.get("job_family_compatibility", True)),
            credentials=bool(gates.get("required_credential_compatibility", True)),
            timing=bool(gates.get("readiness_timing_compatibility", True)),
            geography=bool(gates.get("geography_feasibility", True)),
            min_requirements=bool(gates.get("explicit_minimum_requirement_compatibility", True)),
            seniority=bool(gates.get("seniority_compatibility", True)),
        )

    # Geography unknown-preference handling
    geo_relax = raw.get("geography_relaxation", {})
    if geo_relax:
        cfg.relax_unknown_geo_prefs = bool(geo_relax.get("relax_unknown_prefs", True))

    # Structured/semantic blend
    blend = raw.get("base_fit", {}).get("weights", {})
    if blend:
        s = float(blend.get("structured", 0.75))
        m = float(blend.get("semantic", 0.25))
        total = s + m
        if total > 0:
            cfg.structured_weight = round(s / total, 4)
            cfg.semantic_weight = round(m / total, 4)

    return cfg
