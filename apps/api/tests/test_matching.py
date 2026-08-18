"""
test_matching.py — Unit tests for Phase 4.3 / 5.1 / 5.2 matching engine.

All tests are pure (no DB, no filesystem, no Supabase required).
Tests cover:
  - matching.normalizer  — program/title normalization, pay, location, timing, work setting
  - matching.gates       — all 5 gate evaluators + compute_eligibility aggregation
  - matching.scorer      — all 9 dimension scorers + compute_structured_score
  - matching.engine      — compute_match integration, score formula, match labels

Run with:
  cd apps/api && pytest tests/test_matching.py -v
"""
import sys
from datetime import date
from pathlib import Path

import pytest

# Allow importing from packages/matching
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "packages"))

from matching.config import (
    EligibilityCapConfig,
    NullHandlingConfig,
    ScoringConfig,
    StructuredWeights,
)
from matching.engine import MatchResult, compute_match
from matching.gates import (
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
    evaluate_timing_gate,
)
from matching.normalizer import (
    JOB_FAMILY_ADJACENCY,
    TimingResult,
    normalize_job_title_to_family,
    normalize_location,
    normalize_pay_range,
    normalize_program_to_job_family,
    normalize_timing,
    normalize_work_setting,
)
from matching.scorer import (
    compute_structured_score,
    score_compensation_alignment,
    score_credential_readiness,
    score_experience_alignment,
    score_geography_alignment,
    score_timing_readiness,
    score_trade_program_alignment,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_FAMILIES = [
    {"id": "1", "code": "electrical", "name": "Electrical",
     "aliases": ["electrician", "electrical apprentice", "electrical technician"]},
    {"id": "2", "code": "hvac", "name": "HVAC",
     "aliases": ["hvac technician", "heating and cooling", "refrigeration"]},
    {"id": "3", "code": "plumbing", "name": "Plumbing",
     "aliases": ["plumber", "pipefitter", "plumbing apprentice"]},
    {"id": "4", "code": "automotive", "name": "Automotive",
     "aliases": ["auto technician", "automotive technician", "vehicle mechanic"]},
    {"id": "5", "code": "culinary", "name": "Culinary",
     "aliases": ["cook", "chef", "culinary arts"]},
]

_GEO_REGIONS = [
    {"id": "r1", "code": "midwest", "name": "Midwest",
     "states": ["IL", "IN", "MI", "OH", "WI", "MN", "IA", "MO", "ND", "SD", "NE", "KS"]},
    {"id": "r2", "code": "south", "name": "South",
     "states": ["TX", "OK", "AR", "LA", "MS", "AL", "TN", "KY", "FL", "GA", "SC", "NC", "VA", "WV"]},
    {"id": "r3", "code": "northeast", "name": "Northeast",
     "states": ["NY", "NJ", "PA", "CT", "MA", "RI", "VT", "NH", "ME", "DE", "MD", "DC"]},
    {"id": "r4", "code": "west", "name": "West",
     "states": ["CA", "OR", "WA", "NV", "AZ", "CO", "UT", "NM", "ID", "MT", "WY", "AK", "HI"]},
]


def _default_config() -> ScoringConfig:
    return ScoringConfig()


def _make_applicant(**kwargs) -> dict:
    """Minimal valid applicant dict. available_from_date defaults to the past so
    the timing gate passes by default in engine integration tests."""
    base = {
        "id": "app-001",
        "first_name": "Jane",
        "last_name": "Smith",
        "canonical_job_family_code": "electrical",
        "state": "IL",
        "region": "midwest",
        "willing_to_relocate": False,
        "willing_to_travel": False,
        "expected_completion_date": None,
        "available_from_date": date(2025, 1, 1),  # past → available_now timing gate PASS
        "experience_raw": "Completed 2-year electrical apprenticeship at ABC Electric.",
        "bio_raw": "Passionate about electrical work and seeking first role.",
        "career_goals_raw": "Want to become a licensed journeyman electrician.",
        "program_name_raw": "Electrical Apprentice",
    }
    base.update(kwargs)
    return base


def _make_job(**kwargs) -> dict:
    """Minimal valid job dict."""
    base = {
        "id": "job-001",
        "employer_id": "emp-001",
        "title_raw": "Electrician",
        "title_normalized": "Electrician",
        "canonical_job_family_code": "electrical",
        "state": "IL",
        "region": "midwest",
        "work_setting": "on_site",
        "travel_requirement": None,
        "pay_min": 25.0,
        "pay_max": 35.0,
        "pay_type": "hourly",
        "required_credentials": [],
        "description_raw": None,
    }
    base.update(kwargs)
    return base


def _make_employer(**kwargs) -> dict:
    base = {"id": "emp-001", "name": "ACME Electric", "is_partner": False}
    base.update(kwargs)
    return base


# ===========================================================================
# normalizer.py
# ===========================================================================

class TestNormalizeProgram:
    def test_exact_code_match(self):
        r = normalize_program_to_job_family("electrical", _FAMILIES)
        assert r.family_code == "electrical"
        assert r.confidence == "high"

    def test_exact_name_match_case_insensitive(self):
        r = normalize_program_to_job_family("HVAC", _FAMILIES)
        assert r.family_code == "hvac"
        assert r.confidence == "high"

    def test_alias_substring_match(self):
        r = normalize_program_to_job_family("electrician apprentice", _FAMILIES)
        assert r.family_code == "electrical"

    def test_keyword_overlap_match(self):
        r = normalize_program_to_job_family("Auto Technician Training", _FAMILIES)
        assert r.family_code == "automotive"

    def test_no_match_returns_none(self):
        r = normalize_program_to_job_family("underwater basket weaving", _FAMILIES)
        assert r.family_code is None
        assert r.needs_review is True

    def test_empty_string_returns_none(self):
        r = normalize_program_to_job_family("", _FAMILIES)
        assert r.family_code is None
        assert r.needs_review is True

    def test_none_input_returns_none(self):
        r = normalize_program_to_job_family(None, _FAMILIES)
        assert r.family_code is None

    def test_multiple_alias_matches_sets_needs_review(self):
        # "auto tech" is a substring of "auto technician training" AND
        # "auto technician" is also a substring of "auto technician training"
        # → two families both match via alias → needs_review = True
        families = [
            {"id": "a", "code": "x_family", "name": "X Family", "aliases": ["auto tech"]},
            {"id": "b", "code": "y_family", "name": "Y Family", "aliases": ["auto technician"]},
        ]
        r = normalize_program_to_job_family("auto technician training", families)
        assert r.needs_review is True
        assert len(r.alternative_families) >= 1


class TestNormalizeJobTitle:
    def test_pathway_used_when_high_confidence(self):
        r = normalize_job_title_to_family("Senior Tech", "Electrician", _FAMILIES)
        assert r.family_code == "electrical"
        assert "career_pathway" in r.match_reason

    def test_fallback_to_title_when_no_pathway(self):
        r = normalize_job_title_to_family("HVAC Technician", None, _FAMILIES)
        assert r.family_code == "hvac"

    def test_no_match_when_unrecognized(self):
        r = normalize_job_title_to_family("Yoga Instructor", "Wellness Coach", _FAMILIES)
        assert r.family_code is None
        assert r.needs_review is True


class TestNormalizePayRange:
    def test_hourly_range_with_dash(self):
        # Note: "$22–$33/hr" works (number–number); "$22/hr–$33/hr" doesn't
        # because "/hr" sits between the number and the separator.
        lo, hi, pt = normalize_pay_range("$22 – $33/hr")
        assert (lo, hi, pt) == (22.0, 33.0, "hourly")

    def test_annual_range_with_keyword(self):
        lo, hi, pt = normalize_pay_range("$45,000 – $65,000 annually")
        assert (lo, hi, pt) == (45000.0, 65000.0, "annual")

    def test_single_hourly_value(self):
        lo, hi, pt = normalize_pay_range("$28/hr")
        assert lo == 28.0 and hi == 28.0 and pt == "hourly"

    def test_magnitude_heuristic_hourly(self):
        lo, hi, pt = normalize_pay_range("$18-$25")   # < 500 → hourly
        assert pt == "hourly"

    def test_magnitude_heuristic_annual(self):
        lo, hi, pt = normalize_pay_range("$50,000-$70,000")  # > 500 → annual
        assert pt == "annual"

    def test_none_returns_triple_none(self):
        assert normalize_pay_range(None) == (None, None, None)

    def test_empty_string_returns_triple_none(self):
        assert normalize_pay_range("") == (None, None, None)

    def test_non_numeric_returns_triple_none(self):
        assert normalize_pay_range("competitive") == (None, None, None)


class TestNormalizeLocation:
    def test_illinois_maps_to_midwest(self):
        code = normalize_location("Chicago", "IL", _GEO_REGIONS)
        assert code == "midwest"

    def test_texas_maps_to_south(self):
        code = normalize_location(None, "TX", _GEO_REGIONS)
        assert code == "south"

    def test_missing_state_returns_none(self):
        code = normalize_location("Chicago", None, _GEO_REGIONS)
        assert code is None

    def test_unknown_state_returns_none(self):
        code = normalize_location(None, "XX", _GEO_REGIONS)
        assert code is None

    def test_case_insensitive_state(self):
        code = normalize_location(None, "il", _GEO_REGIONS)
        assert code == "midwest"


class TestNormalizeTiming:
    _TODAY = date(2026, 3, 10)

    def test_past_date_is_available_now(self):
        r = normalize_timing(date(2025, 6, 1), None, self._TODAY)
        assert r.readiness_label == "available_now"
        assert r.months_to_available == 0

    def test_today_is_available_now(self):
        r = normalize_timing(self._TODAY, None, self._TODAY)
        assert r.readiness_label == "available_now"

    def test_near_completion(self):
        future = date(2026, 5, 10)  # 2 months out
        r = normalize_timing(future, None, self._TODAY)
        assert r.readiness_label == "near_completion"
        assert r.months_to_available < 4

    def test_in_progress(self):
        future = date(2026, 9, 10)  # ~6 months out
        r = normalize_timing(future, None, self._TODAY)
        assert r.readiness_label == "in_progress"

    def test_future(self):
        future = date(2029, 6, 1)  # >24 months out (the "future" threshold)
        r = normalize_timing(future, None, self._TODAY)
        assert r.readiness_label == "future"

    def test_no_dates_returns_unknown(self):
        r = normalize_timing(None, None, self._TODAY)
        assert r.readiness_label == "unknown"
        assert r.months_to_available is None

    def test_available_from_date_takes_priority(self):
        # available_from is in the past, completion is in the future
        r = normalize_timing(date(2026, 12, 1), date(2025, 1, 1), self._TODAY)
        assert r.readiness_label == "available_now"

    def test_is_enrolled_set_for_future_date(self):
        future = date(2026, 7, 1)
        r = normalize_timing(future, None, self._TODAY)
        assert r.is_currently_enrolled is True

    def test_is_enrolled_false_for_past_date(self):
        r = normalize_timing(date(2025, 1, 1), None, self._TODAY)
        assert r.is_currently_enrolled is False


class TestNormalizeWorkSetting:
    def test_no_returns_on_site(self):
        assert normalize_work_setting("No") == "on_site"

    def test_yes_returns_remote(self):
        assert normalize_work_setting("Yes") == "remote"

    def test_hybrid(self):
        assert normalize_work_setting("Hybrid") == "hybrid"

    def test_fully_remote(self):
        assert normalize_work_setting("Fully Remote") == "remote"

    def test_none_returns_none(self):
        assert normalize_work_setting(None) is None

    def test_unrecognised_returns_none(self):
        assert normalize_work_setting("occasional") is None


# ===========================================================================
# gates.py
# ===========================================================================

class TestJobFamilyGate:
    def test_direct_match_passes(self):
        g = evaluate_job_family_gate("electrical", "electrical")
        assert g.result == PASS

    def test_adjacent_families_near_fit(self):
        # electrical is adjacent to hvac
        g = evaluate_job_family_gate("electrical", "hvac")
        assert g.result == NEAR_FIT

    def test_unrelated_fails(self):
        g = evaluate_job_family_gate("electrical", "culinary")
        assert g.result == FAIL
        assert g.severity == "critical"

    def test_null_applicant_family_near_fit(self):
        g = evaluate_job_family_gate(None, "electrical")
        assert g.result == NEAR_FIT
        assert g.needs_review is True

    def test_null_job_family_near_fit(self):
        g = evaluate_job_family_gate("electrical", None)
        assert g.result == NEAR_FIT

    def test_both_null_near_fit(self):
        g = evaluate_job_family_gate(None, None)
        assert g.result == NEAR_FIT


class TestCredentialGate:
    def test_no_required_credentials_passes(self):
        g = evaluate_credential_gate([], {"program_name_raw": "Electrician"})
        assert g.result == PASS

    def test_none_credentials_passes(self):
        g = evaluate_credential_gate(None, {})
        assert g.result == PASS

    def test_required_creds_with_program_near_fit(self):
        g = evaluate_credential_gate(["EPA 608"], {"program_name_raw": "HVAC Tech"})
        assert g.result == NEAR_FIT

    def test_required_creds_unverified_near_fit(self):
        # Required credential, but the applicant's certs aren't verified yet →
        # near-fit (not a hard fail — they may hold it).
        g = evaluate_credential_gate(["EPA 608"], {})
        assert g.result == NEAR_FIT


class TestTimingGate:
    def test_available_now_passes(self):
        timing = TimingResult(0, "available_now", False)
        g = evaluate_timing_gate(timing)
        assert g.result == PASS

    def test_near_completion_within_3_months_passes(self):
        # ≤3 months out is within the typical hiring window → PASS.
        timing = TimingResult(2, "near_completion", True)
        g = evaluate_timing_gate(timing)
        assert g.result == PASS

    def test_in_progress_near_fit(self):
        timing = TimingResult(6, "in_progress", True)
        g = evaluate_timing_gate(timing)
        assert g.result == NEAR_FIT

    def test_future_fails(self):
        timing = TimingResult(15, "future", True)
        g = evaluate_timing_gate(timing)
        assert g.result == FAIL
        assert g.severity == "critical"

    def test_unknown_passes_null_handling(self):
        # Unknown timing is not a reason to block — assume available (PASS).
        timing = TimingResult(None, "unknown", False)
        g = evaluate_timing_gate(timing)
        assert g.result == PASS


class TestGeographyGate:
    def test_remote_job_passes(self):
        g = evaluate_geography_gate("TX", "south", False, False,
                                    "CA", "west", "remote")
        assert g.result == PASS

    def test_same_state_passes(self):
        g = evaluate_geography_gate("IL", "midwest", False, False,
                                    "IL", "midwest", "on_site")
        assert g.result == PASS

    def test_same_region_willing_to_relocate_passes(self):
        g = evaluate_geography_gate("IL", "midwest", True, False,
                                    "OH", "midwest", "on_site")
        assert g.result == PASS

    def test_same_region_not_willing_fails(self):
        # Same region, different state, unwilling to relocate or travel out of
        # state → critical geography failure (see the gate's decision matrix).
        g = evaluate_geography_gate("IL", "midwest", False, False,
                                    "OH", "midwest", "on_site")
        assert g.result == FAIL
        assert g.severity == "critical"

    def test_different_region_willing_near_fit(self):
        g = evaluate_geography_gate("IL", "midwest", True, False,
                                    "TX", "south", "on_site")
        assert g.result == NEAR_FIT

    def test_different_region_not_willing_fails(self):
        g = evaluate_geography_gate("IL", "midwest", False, False,
                                    "TX", "south", "on_site")
        assert g.result == FAIL
        assert g.severity == "critical"

    def test_no_location_data_passes(self):
        # Job location unspecified → geography can't be assessed, so the gate
        # doesn't block (the scorer applies a neutral default instead).
        g = evaluate_geography_gate(None, None, False, False, None, None, "on_site")
        assert g.result == PASS


class TestMinReqGate:
    def test_no_description_passes(self):
        g = evaluate_min_req_gate({}, None)
        assert g.result == PASS

    def test_description_present_without_extraction_passes_for_review(self):
        # No extracted skills to compare against → don't block on absence of
        # evidence; PASS but flag for admin review to run extraction.
        g = evaluate_min_req_gate({}, "Must have EPA 608 cert and 2 years experience.")
        assert g.result == PASS
        assert g.needs_review is True


class TestComputeEligibility:
    def _config(self):
        return EligibilityCapConfig()

    def test_all_pass_returns_eligible(self):
        gates = [
            GateDetail("g1", PASS, "ok"),
            GateDetail("g2", PASS, "ok"),
        ]
        r = compute_eligibility(gates, self._config())
        assert r.eligibility_status == ELIGIBLE
        assert r.hard_gate_cap == 1.0

    def test_one_near_fit_returns_near_fit(self):
        gates = [
            GateDetail("g1", PASS, "ok"),
            GateDetail("g2", NEAR_FIT, "gap"),
        ]
        r = compute_eligibility(gates, self._config())
        assert r.eligibility_status == NEAR_FIT_LABEL
        assert r.hard_gate_cap == 0.75

    def test_one_fail_returns_ineligible(self):
        gates = [
            GateDetail("g1", PASS, "ok"),
            GateDetail("g2", FAIL, "mismatch"),
        ]
        r = compute_eligibility(gates, self._config())
        assert r.eligibility_status == INELIGIBLE
        assert r.hard_gate_cap == 0.35

    def test_fail_overrides_near_fit(self):
        gates = [
            GateDetail("g1", NEAR_FIT, "gap"),
            GateDetail("g2", FAIL, "critical mismatch", severity="critical"),
        ]
        r = compute_eligibility(gates, self._config())
        assert r.eligibility_status == INELIGIBLE

    def test_hard_gate_failures_property(self):
        gates = [
            GateDetail("g1", FAIL, "bad mismatch", severity="critical"),
            GateDetail("g2", PASS, "ok"),
        ]
        r = compute_eligibility(gates, self._config())
        failures = r.hard_gate_failures
        assert len(failures) == 1
        assert failures[0]["gate"] == "g1"

    def test_requires_review_flag(self):
        gates = [
            GateDetail("g1", NEAR_FIT, "unknown", needs_review=True),
        ]
        r = compute_eligibility(gates, self._config())
        assert r.requires_review is True


# ===========================================================================
# scorer.py
# ===========================================================================

class TestScoreTradeAlignment:
    def test_direct_match_100(self):
        d = score_trade_program_alignment("electrical", "electrical", 25, 50)
        assert d.raw_score == 100.0
        assert d.null_handling_applied is False

    def test_adjacent_match_60(self):
        d = score_trade_program_alignment("electrical", "hvac", 25, 50)
        assert d.raw_score == 60.0

    def test_unrelated_20(self):
        d = score_trade_program_alignment("electrical", "culinary", 25, 50)
        assert d.raw_score == 20.0

    def test_null_applicant_uses_default(self):
        d = score_trade_program_alignment(None, "electrical", 25, 50)
        assert d.null_handling_applied is True
        assert d.raw_score == 50.0

    def test_weighted_score_formula(self):
        d = score_trade_program_alignment("electrical", "electrical", 25, 50)
        assert d.weighted_score == pytest.approx(25.0)  # 25 * 100 / 100


class TestScoreGeographyAlignment:
    def _nh(self):
        return NullHandlingConfig()

    def test_remote_job_90(self):
        d = score_geography_alignment("IL", "midwest", False, False,
                                      "CA", "west", "remote", 20, self._nh())
        assert d.raw_score == 90.0

    def test_same_state_100(self):
        d = score_geography_alignment("IL", "midwest", False, False,
                                      "IL", "midwest", "on_site", 20, self._nh())
        assert d.raw_score == 100.0

    def test_same_region_willing_to_relocate_85(self):
        # willing_to_relocate → relocation preference "anywhere" → 85 within region
        d = score_geography_alignment("IL", "midwest", True, False,
                                      "OH", "midwest", "on_site", 20, self._nh())
        assert d.raw_score == 85.0

    def test_diff_region_willing_to_relocate_70(self):
        # Different region, open to relocating anywhere → 70
        d = score_geography_alignment("IL", "midwest", True, False,
                                      "TX", "south", "on_site", 20, self._nh())
        assert d.raw_score == 70.0

    def test_no_location_uses_null_default(self):
        d = score_geography_alignment(None, None, False, False,
                                      None, None, "on_site", 20, self._nh())
        assert d.null_handling_applied is True
        assert d.raw_score == 35.0  # geography_fully_unknown default


class TestScoreCredentialReadiness:
    def test_no_creds_returns_80(self):
        d = score_credential_readiness([], 15, 50)
        assert d.raw_score == 80.0
        assert d.null_handling_applied is False

    def test_required_creds_pending_scores_not_yet_verified(self):
        # Unverified required credential is scored concretely (40), not treated
        # as a null default.
        d = score_credential_readiness(["EPA 608"], 15, 50)
        assert d.null_handling_applied is False
        assert d.raw_score == 40.0


class TestScoreTimingReadiness:
    def test_available_now_100(self):
        timing = TimingResult(0, "available_now", False)
        d = score_timing_readiness(timing, 10, 50)
        assert d.raw_score == 100.0

    def test_near_completion_90(self):
        timing = TimingResult(2, "near_completion", True)
        d = score_timing_readiness(timing, 10, 50)
        assert d.raw_score == 90.0

    def test_in_progress_scales(self):
        timing = TimingResult(8, "in_progress", True)
        d = score_timing_readiness(timing, 10, 50)
        assert 40.0 <= d.raw_score <= 75.0

    def test_future_20(self):
        timing = TimingResult(15, "future", True)
        d = score_timing_readiness(timing, 10, 50)
        assert d.raw_score == 20.0

    def test_unknown_uses_null_default(self):
        timing = TimingResult(None, "unknown", False)
        d = score_timing_readiness(timing, 10, 50)
        assert d.null_handling_applied is True
        assert d.raw_score == 50.0


class TestScoreExperienceAlignment:
    def test_experience_and_internship_85(self):
        d = score_experience_alignment("Completed electrical apprenticeship at XYZ.", None, True, 10, 50)
        assert d.raw_score == 85.0

    def test_experience_only_65(self):
        d = score_experience_alignment("Worked in electrical trade for 2 years.", None, None, 10, 50)
        assert d.raw_score == 65.0

    def test_bio_only_55(self):
        d = score_experience_alignment(None, "I am passionate about electrical work and learning.", None, 10, 50)
        assert d.raw_score == 55.0

    def test_no_data_defaults_to_trade_training_baseline(self):
        # New grads with no experience text aren't penalized — trade training
        # counts as foundational experience (55). It IS flagged as a default:
        # a population-wide constant is not applicant evidence, and the
        # evidence-weighted aggregate must be able to exclude it.
        d = score_experience_alignment(None, None, None, 10, 50)
        assert d.null_handling_applied is True
        assert d.raw_score == 55.0

    def test_short_experience_uses_training_baseline(self):
        # Sub-threshold text carries no signal either — same flagged default.
        d = score_experience_alignment("Tech", None, None, 10, 50)
        assert d.null_handling_applied is True
        assert d.raw_score == 55.0


class TestScoreCompensationAlignment:
    def test_no_pay_data_null_default(self):
        d = score_compensation_alignment(None, None, None, 5, 70)
        assert d.null_handling_applied is True
        assert d.raw_score == 70.0

    def test_competitive_hourly_75(self):
        d = score_compensation_alignment(22.0, 30.0, "hourly", 5, 70)
        assert d.raw_score == 75.0

    def test_competitive_annual_75(self):
        d = score_compensation_alignment(45000.0, 65000.0, "annual", 5, 70)
        assert d.raw_score == 75.0

    def test_low_hourly_uses_null_default(self):
        d = score_compensation_alignment(10.0, 14.0, "hourly", 5, 70)
        assert d.null_handling_applied is True


class TestComputeStructuredScore:
    def test_perfect_match_score_above_70(self):
        app = _make_applicant(
            state="IL", region="midwest",
            willing_to_relocate=False, willing_to_travel=False,
            experience_raw="2-year electrical apprenticeship completed at ACME.",
        )
        job = _make_job(
            state="IL", region="midwest",
            work_setting="on_site",
            pay_min=25.0, pay_max=35.0, pay_type="hourly",
            required_credentials=[],
        )
        timing = TimingResult(0, "available_now", False)
        config = _default_config()
        score, dims, _ = compute_structured_score(app, job, timing, config)
        assert score > 70.0
        assert len(dims) == 9

    def test_mismatched_family_lowers_score(self):
        app = _make_applicant(canonical_job_family_code="culinary")
        job = _make_job(canonical_job_family_code="electrical")
        timing = TimingResult(0, "available_now", False)
        config = _default_config()
        score_bad, _, _ = compute_structured_score(app, job, timing, config)

        app2 = _make_applicant(canonical_job_family_code="electrical")
        score_good, _, _ = compute_structured_score(app2, job, timing, config)
        assert score_bad < score_good

    def test_dimension_count_always_nine(self):
        app = _make_applicant()
        job = _make_job()
        timing = TimingResult(None, "unknown", False)
        _, dims, _ = compute_structured_score(app, job, timing, _default_config())
        assert len(dims) == 9

    def test_total_is_evidence_weighted_mean(self):
        app = _make_applicant()
        job = _make_job()
        timing = TimingResult(0, "available_now", False)
        total, dims, _ = compute_structured_score(app, job, timing, _default_config())
        known = [d for d in dims if not d.null_handling_applied]
        expected = sum(d.weight * d.raw_score for d in known) / sum(d.weight for d in known)
        assert total == pytest.approx(min(100.0, expected), abs=0.01)

    def test_score_bounded_0_to_100(self):
        for _ in range(3):
            app = _make_applicant()
            job = _make_job()
            timing = TimingResult(0, "available_now", False)
            score, _, _ = compute_structured_score(app, job, timing, _default_config())
            assert 0.0 <= score <= 100.0


# ===========================================================================
# engine.py — compute_match integration
# ===========================================================================

class TestComputeMatch:
    _TODAY = date(2026, 3, 10)

    def test_eligible_pair_produces_match_result(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert isinstance(result, MatchResult)
        assert result.eligibility_status == ELIGIBLE
        assert result.hard_gate_cap == 1.0

    def test_ineligible_pair_from_family_mismatch(self):
        app = _make_applicant(canonical_job_family_code="culinary")
        job = _make_job(canonical_job_family_code="electrical",
                        state="TX", region="south",
                        description_raw=None)
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY,
                               scoring_run_id="test-run-001")
        assert result.eligibility_status == INELIGIBLE
        assert result.hard_gate_cap == 0.35

    def test_ineligible_label_is_low_fit(self):
        app = _make_applicant(canonical_job_family_code="culinary",
                              state="IL", region="midwest",
                              willing_to_relocate=False)
        job = _make_job(canonical_job_family_code="electrical",
                        state="TX", region="south")
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert result.match_label == "low_fit"

    def test_base_fit_score_formula(self):
        """base_fit = hard_gate_cap * (struct * 0.75 + semantic * 0.25)"""
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        expected_base = result.hard_gate_cap * (
            result.weighted_structured_score * 0.75
            + result.semantic_score * 0.25
        )
        assert result.base_fit_score == pytest.approx(expected_base, abs=0.01)

    def test_policy_adjusted_score_is_separate(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer(is_partner=True)
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        # Partner modifier should push policy_adjusted above base (or at least stored separately)
        assert hasattr(result, "base_fit_score")
        assert hasattr(result, "policy_adjusted_score")

    def test_partner_employer_boosts_policy_score(self):
        app = _make_applicant()
        job = _make_job()
        emp_no = _make_employer(is_partner=False)
        emp_yes = _make_employer(is_partner=True)
        r_no = compute_match(app, job, emp_no, _default_config(), self._TODAY)
        r_yes = compute_match(app, job, emp_yes, _default_config(), self._TODAY)
        assert r_yes.policy_adjusted_score >= r_no.policy_adjusted_score

    def test_dimension_scores_length(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert len(result.dimension_scores) == 9

    def test_hard_gate_cap_applied_to_base_fit(self):
        # near_fit applicant (future timing)
        future_date = date(2027, 6, 1)
        # commute_radius_miles set → the applicant has STATED a geography
        # preference, so the different-region no-relocation FAIL still holds
        # (the unknown-prefs relaxation only applies to unstated preferences).
        app = _make_applicant(
            expected_completion_date=future_date, available_from_date=None,
            commute_radius_miles=25,
        )
        job = _make_job(state="TX", region="south")
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        # geography mismatch TX vs IL, stated stay-home preference → FAIL
        assert result.eligibility_status == INELIGIBLE

    def test_match_label_strong_fit_above_80(self):
        """Force a scenario where policy_adjusted_score should be >= 80."""
        # Same state, same family, available_now, partner, competitive pay
        app = _make_applicant(
            state="IL", region="midwest",
            willing_to_relocate=False, willing_to_travel=False,
            expected_completion_date=None,
            available_from_date=date(2025, 1, 1),
            experience_raw="Completed 2-year electrical apprenticeship at ACME Electric Co.",
        )
        job = _make_job(
            state="IL", region="midwest",
            work_setting="on_site",
            pay_min=28.0, pay_max=40.0, pay_type="hourly",
            required_credentials=[],
        )
        emp = _make_employer(is_partner=True)
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert result.eligibility_status == ELIGIBLE
        assert result.match_label == "strong_fit"

    def test_scoring_run_id_stored_on_result(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY,
                               scoring_run_id="fixed-run-id")
        assert result.scoring_run_id == "fixed-run-id"

    def test_confidence_level_set(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert result.confidence_level in ("high", "medium", "low")

    def test_top_strengths_and_gaps_are_lists(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert isinstance(result.top_strengths, list)
        assert isinstance(result.top_gaps, list)

    def test_recommended_next_step_is_string(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert isinstance(result.recommended_next_step, str)
        assert len(result.recommended_next_step) > 0

    def test_policy_score_capped_at_100(self):
        app = _make_applicant()
        job = _make_job()
        emp = _make_employer(is_partner=True)
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert result.policy_adjusted_score <= 100.0

    def test_policy_score_not_below_zero(self):
        app = _make_applicant(canonical_job_family_code="culinary",
                              state="ME", region="northeast",
                              willing_to_relocate=False)
        job = _make_job(canonical_job_family_code="automotive",
                        state="CA", region="west")
        emp = _make_employer()
        result = compute_match(app, job, emp, _default_config(), self._TODAY)
        assert result.policy_adjusted_score >= 0.0


# ===========================================================================
# config.py
# ===========================================================================

class TestScoringConfig:
    def test_default_config_loads(self):
        cfg = ScoringConfig()
        assert cfg.version == "v1"
        assert cfg.structured_weight == 0.75
        assert cfg.semantic_weight == 0.25

    def test_default_weights_sum_to_100(self):
        w = StructuredWeights()
        total = (
            w.trade_program_alignment
            + w.geography_alignment
            + w.credential_readiness
            + w.timing_readiness
            + w.experience_internship_alignment
            + w.industry_alignment
            + w.compensation_alignment
            + w.work_style_signal_alignment
            + w.employer_soft_pref_alignment
        )
        assert total == pytest.approx(100.0)

    def test_structured_plus_semantic_weight_equals_1(self):
        cfg = ScoringConfig()
        assert cfg.structured_weight + cfg.semantic_weight == pytest.approx(1.0)

    def test_eligibility_caps_ordering(self):
        caps = EligibilityCapConfig()
        assert caps.eligible > caps.near_fit > caps.ineligible > 0


# ===========================================================================
# JOB_FAMILY_ADJACENCY integrity
# ===========================================================================

class TestJobFamilyAdjacency:
    def test_known_adjacencies_present(self):
        """Spot-check key adjacency relationships used by gate + scorer."""
        assert "hvac" in JOB_FAMILY_ADJACENCY["electrical"]
        assert "construction" in JOB_FAMILY_ADJACENCY["electrical"]
        assert "plumbing" in JOB_FAMILY_ADJACENCY["hvac"]
        assert "automotive" in JOB_FAMILY_ADJACENCY["welding"]

    def test_known_non_adjacencies(self):
        """Unrelated families must NOT appear in each other's adjacent set."""
        assert "culinary" not in JOB_FAMILY_ADJACENCY.get("electrical", set())
        assert "electrical" not in JOB_FAMILY_ADJACENCY.get("culinary", set())

    def test_no_self_adjacency(self):
        for family, adjacent_set in JOB_FAMILY_ADJACENCY.items():
            assert family not in adjacent_set, (
                f"{family} is listed as adjacent to itself"
            )


# ===========================================================================
# Progressive relaxation: tiers, geo unknown-preference rule, config plumbing
# ===========================================================================

from matching.config import (  # noqa: E402
    GatesEnabledConfig,
    MatchLabelConfig,
    RelaxationConfig,
    _from_yaml,
    config_to_dict,
    normalize_weights,
    validate_config_dict,
)


def _coords_applicant(**kwargs) -> dict:
    """Applicant with coordinates and NO stated geography preferences —
    the imported-scholar shape (radius NULL, no states, willing flags false)."""
    base = _make_applicant(
        city="Shelton", state="CT", region="northeast",
        lat=41.30, lng=-73.10,
        willing_to_relocate=False, willing_to_travel=False,
        relocation_preference="stay_current", travel_preference="no_travel",
    )
    base.update(kwargs)
    return base


def _coords_job(**kwargs) -> dict:
    base = _make_job(
        city="Bridgeport", state="CT", region="northeast",
        lat=41.19, lng=-73.20, work_setting="on_site",
        experience_level="entry",
    )
    base.update(kwargs)
    return base


_FAR_JOB = dict(city="Louisville", state="KY", region="south", lat=38.25, lng=-85.76)
_TODAY = date(2026, 8, 1)


class TestGeoUnknownPrefsRelaxation:
    """Beyond-radius with UNSTATED geography preferences is missing data →
    NEAR_FIT, never a silent hard FAIL. Stated preferences keep the FAIL."""

    def test_unstated_prefs_beyond_radius_is_near_fit(self):
        app = _coords_applicant()          # no radius, no states, not willing
        job = _coords_job(**_FAR_JOB)      # ~600 mi away
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        geo = r.hard_gate_rationale["geography_feasibility"]
        assert geo["result"] == "near_fit"
        assert "set your commute radius" in geo["reason"]

    def test_stated_radius_beyond_radius_still_fails(self):
        app = _coords_applicant(commute_radius_miles=25)   # stated preference
        job = _coords_job(**_FAR_JOB)
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.hard_gate_rationale["geography_feasibility"]["result"] == "fail"
        assert r.eligibility_status == INELIGIBLE

    def test_relaxation_flag_off_restores_hard_fail(self):
        cfg = _default_config()
        cfg.relax_unknown_geo_prefs = False
        app = _coords_applicant()
        job = _coords_job(**_FAR_JOB)
        r = compute_match(app, job, _make_employer(), cfg, _TODAY)
        assert r.hard_gate_rationale["geography_feasibility"]["result"] == "fail"

    def test_relaxation_never_raises_base_fit(self):
        """The relaxed pair may gain visibility but its base fit stays capped
        by near_fit (0.75), i.e. relaxation is not a score bonus."""
        app = _coords_applicant()
        job = _coords_job(**_FAR_JOB)
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.hard_gate_cap <= 0.75

    def test_willing_to_relocate_counts_as_stated(self):
        app = _coords_applicant(willing_to_relocate=True)
        job = _coords_job(**_FAR_JOB)
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        # willing → beyond-radius PASS branch, not the unknown-prefs branch
        assert r.hard_gate_rationale["geography_feasibility"]["result"] == "pass"


class TestTierAdmission:
    """Tier semantics: strict / adjacent / stretch / nearby / None.
    Tiers group visibility only — they never alter scores."""

    def test_eligible_is_strict_tier(self):
        app = _coords_applicant(canonical_job_family_code="manufacturing")
        job = _coords_job(canonical_job_family_code="manufacturing")
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.eligibility_status == ELIGIBLE
        assert r.match_tier == "strict"

    def test_adjacent_trade_nearby_is_adjacent_tier(self):
        app = _coords_applicant(canonical_job_family_code="welding")
        job = _coords_job(canonical_job_family_code="manufacturing")
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.eligibility_status == NEAR_FIT_LABEL
        assert r.match_tier == "adjacent"

    def test_unrelated_trade_nearby_is_nearby_tier(self):
        app = _coords_applicant(canonical_job_family_code="nursing",
                                program_name_raw="Nursing")
        job = _coords_job(canonical_job_family_code="manufacturing")
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.eligibility_status == INELIGIBLE       # score stays capped
        assert r.match_tier == "nearby"
        assert r.tier_reason == "Near you, different trade"
        assert r.hard_gate_cap == 0.35                  # honesty: no promotion

    def test_unrelated_trade_far_away_gets_no_tier(self):
        app = _coords_applicant(canonical_job_family_code="nursing")
        job = _coords_job(canonical_job_family_code="manufacturing", **_FAR_JOB)
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.match_tier is None

    def test_nearby_tier_requires_other_gates_clean(self):
        """A nearby unrelated-trade job that ALSO fails seniority must not
        surface — 'near you' never overrides a second hard failure."""
        app = _coords_applicant(canonical_job_family_code="nursing")
        job = _coords_job(canonical_job_family_code="manufacturing",
                          experience_level="senior")
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.match_tier is None

    def test_tier_nearby_can_be_disabled(self):
        cfg = _default_config()
        cfg.relaxation = RelaxationConfig(tier_nearby=False)
        app = _coords_applicant(canonical_job_family_code="nursing")
        job = _coords_job(canonical_job_family_code="manufacturing")
        r = compute_match(app, job, _make_employer(), cfg, _TODAY)
        assert r.match_tier is None

    def test_distance_miles_recorded(self):
        app = _coords_applicant()
        job = _coords_job()
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.distance_miles is not None and 0 < r.distance_miles < 25


class TestGateToggles:
    def test_disabled_geography_gate_passes(self):
        cfg = _default_config()
        cfg.gates_enabled = GatesEnabledConfig(geography=False)
        app = _coords_applicant(commute_radius_miles=25)
        job = _coords_job(**_FAR_JOB)
        r = compute_match(app, job, _make_employer(), cfg, _TODAY)
        geo = r.hard_gate_rationale["geography_feasibility"]
        assert geo["result"] == "pass"
        assert "disabled by admin policy" in geo["reason"]

    def test_disabled_seniority_gate_passes(self):
        cfg = _default_config()
        cfg.gates_enabled = GatesEnabledConfig(seniority=False)
        app = _coords_applicant()
        job = _coords_job(experience_level="senior")
        r = compute_match(app, job, _make_employer(), cfg, _TODAY)
        assert r.hard_gate_rationale["seniority_compatibility"]["result"] == "pass"


class TestSeniorityLevelAliases:
    def test_experienced_maps_to_mid(self):
        from matching.gates import evaluate_seniority_gate
        g = evaluate_seniority_gate("Experienced", 0, is_trade_school=True)
        assert g.result == NEAR_FIT   # mid-level for a new grad

    def test_fresh_graduate_maps_to_entry(self):
        from matching.gates import evaluate_seniority_gate
        g = evaluate_seniority_gate("Fresh Graduate", 0, is_trade_school=True)
        assert g.result == PASS


class TestLabelThresholdsConfig:
    def test_labels_come_from_config(self):
        cfg = _default_config()
        cfg.match_labels = MatchLabelConfig(strong_fit_min=90, good_fit_min=70,
                                            moderate_fit_min=50)
        app = _coords_applicant(canonical_job_family_code="manufacturing")
        job = _coords_job(canonical_job_family_code="manufacturing")
        r = compute_match(app, job, _make_employer(), cfg, _TODAY)
        # Same pair under stricter thresholds gets an equal-or-lower label
        r_default = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        order = ["low_fit", "moderate_fit", "good_fit", "strong_fit"]
        assert order.index(r.match_label) <= order.index(r_default.match_label)

    def test_near_fit_never_strong(self):
        from matching.engine import _compute_match_label
        assert _compute_match_label(95.0, NEAR_FIT_LABEL) == "good_fit"
        assert _compute_match_label(95.0, ELIGIBLE) == "strong_fit"
        assert _compute_match_label(95.0, INELIGIBLE) == "low_fit"


class TestConfigPlumbing:
    def test_round_trip_serialization(self):
        cfg = ScoringConfig()
        cfg.relaxation = RelaxationConfig(min_results=7, tier_nearby=False)
        cfg.match_labels = MatchLabelConfig(strong_fit_min=85)
        cfg.relax_unknown_geo_prefs = False
        d = config_to_dict(cfg)
        cfg2 = _from_yaml(d)
        assert cfg2.relaxation == cfg.relaxation
        assert cfg2.match_labels == cfg.match_labels
        assert cfg2.relax_unknown_geo_prefs is False
        assert cfg2.structured_weights == cfg.structured_weights
        assert cfg2.gates_enabled == cfg.gates_enabled

    def test_normalize_weights_sums_to_100(self):
        nw = normalize_weights({"trade_program_alignment": 3, "geography_alignment": 1})
        assert sum(nw.values()) == pytest.approx(100.0)
        assert nw["trade_program_alignment"] == pytest.approx(75.0)

    def test_from_yaml_normalizes_drifted_weights(self):
        d = config_to_dict(ScoringConfig())
        d["structured_score"]["weights"]["trade_program_alignment"] = 50  # sum=125
        cfg = _from_yaml(d)
        total = sum(
            getattr(cfg.structured_weights, k)
            for k in d["structured_score"]["weights"]
        )
        assert total == pytest.approx(100.0)

    def test_validate_rejects_bad_weight_sum(self):
        d = config_to_dict(ScoringConfig())
        d["structured_score"]["weights"]["trade_program_alignment"] = 90
        errors = validate_config_dict(d)
        assert any("sum to 100" in e for e in errors)

    def test_validate_rejects_disordered_labels(self):
        d = config_to_dict(ScoringConfig())
        d["match_labels"] = {"strong_fit_min": 50, "good_fit_min": 60, "moderate_fit_min": 40}
        assert any("moderate < good < strong" in e for e in validate_config_dict(d))

    def test_validate_rejects_disordered_caps(self):
        d = config_to_dict(ScoringConfig())
        d["eligibility"]["labels"]["ineligible"]["hard_gate_cap"] = 0.9
        d["eligibility"]["labels"]["near_fit"]["hard_gate_cap"] = 0.5
        assert any("caps" in e for e in validate_config_dict(d))

    def test_validate_rejects_bad_min_results(self):
        d = config_to_dict(ScoringConfig())
        d["relaxation"]["min_results"] = 999
        assert any("min_results" in e for e in validate_config_dict(d))

    def test_validate_accepts_defaults(self):
        assert validate_config_dict(config_to_dict(ScoringConfig())) == []


class TestNearbyTierProximityVerification:
    """The nearby tier requires VERIFIED proximity — a geography-gate PASS
    for 'location not assessed' or remote jobs must never read 'Near you'."""

    def test_unassessed_foreign_location_never_nearby(self):
        # Job with no state (e.g. Windsor, Ontario) — geo gate passes as
        # "not assessed", distance is 500+ mi. Must NOT be nearby.
        app = _coords_applicant(canonical_job_family_code="nursing")
        job = _coords_job(canonical_job_family_code="manufacturing",
                          city="Windsor", state=None, region=None,
                          lat=42.30, lng=-83.03)
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.hard_gate_rationale["geography_feasibility"]["result"] == "pass"
        assert r.match_tier is None

    def test_remote_job_never_nearby(self):
        app = _coords_applicant(canonical_job_family_code="nursing")
        job = _coords_job(canonical_job_family_code="manufacturing",
                          work_setting="remote", **_FAR_JOB)
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.match_tier is None

    def test_no_coordinates_never_nearby(self):
        app = _coords_applicant(canonical_job_family_code="nursing")
        job = _coords_job(canonical_job_family_code="manufacturing",
                          lat=None, lng=None)
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.match_tier is None

    def test_just_beyond_radius_within_cap_is_nearby(self):
        # ~63 mi away (New Britain CT from Shelton) — beyond the default
        # 50 mi radius but inside nearby_max_miles=75, unrelated trade.
        app = _coords_applicant(canonical_job_family_code="nursing")
        job = _coords_job(canonical_job_family_code="manufacturing",
                          city="Norwich", lat=41.52, lng=-72.08)
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.distance_miles is not None and 50 < r.distance_miles <= 75
        assert r.match_tier == "nearby"

    def test_beyond_cap_not_nearby(self):
        cfg = _default_config()
        cfg.relaxation = RelaxationConfig(nearby_max_miles=30)
        app = _coords_applicant(canonical_job_family_code="nursing")
        job = _coords_job(canonical_job_family_code="manufacturing",
                          city="Norwich", lat=41.52, lng=-72.08)  # ~60 mi
        r = compute_match(app, job, _make_employer(), cfg, _TODAY)
        assert r.match_tier is None

    def test_applicant_radius_can_extend_cap(self):
        cfg = _default_config()
        cfg.relaxation = RelaxationConfig(nearby_max_miles=30)
        app = _coords_applicant(canonical_job_family_code="nursing",
                                commute_radius_miles=100)
        job = _coords_job(canonical_job_family_code="manufacturing",
                          city="Norwich", lat=41.52, lng=-72.08)  # ~60 mi
        r = compute_match(app, job, _make_employer(), cfg, _TODAY)
        assert r.match_tier == "nearby"

    def test_nearby_max_miles_round_trips_and_validates(self):
        cfg = ScoringConfig()
        cfg.relaxation = RelaxationConfig(nearby_max_miles=120)
        d = config_to_dict(cfg)
        assert _from_yaml(d).relaxation.nearby_max_miles == 120
        d["relaxation"]["nearby_max_miles"] = 999
        assert any("nearby_max_miles" in e for e in validate_config_dict(d))


class TestEtlDefaultPrefsAreUnstated:
    """The scholarship import blankets travel_preference='within_state' and
    relocation_preference='stay_current' onto every row — those exact values
    must read as UNSTATED so the geography relaxation applies (audit: 336/337
    applicants carry them verbatim)."""

    def test_etl_default_combo_relaxes_beyond_radius(self):
        app = _coords_applicant(travel_preference="within_state",
                                relocation_preference="stay_current",
                                relocation_states=[])
        job = _coords_job(**_FAR_JOB)
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.hard_gate_rationale["geography_feasibility"]["result"] == "near_fit"

    def test_affirmative_travel_pref_counts_as_stated(self):
        # 'regional' is only reachable via an affirmative profile choice
        app = _coords_applicant(travel_preference="regional",
                                commute_radius_miles=25)
        job = _coords_job(**_FAR_JOB)
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.hard_gate_rationale["geography_feasibility"]["result"] == "fail"

    def test_adjacent_tier_wording_requires_verified_proximity(self):
        # Related trade + geography "not assessed" (no job state, far away):
        # tier stays adjacent but must NOT claim "near you".
        app = _coords_applicant(canonical_job_family_code="welding")
        job = _coords_job(canonical_job_family_code="manufacturing",
                          city="Oakville", state=None, region=None,
                          lat=43.45, lng=-79.68)
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.match_tier == "adjacent"
        assert "near you" not in (r.tier_reason or "")

    def test_adjacent_tier_wording_with_verified_proximity(self):
        app = _coords_applicant(canonical_job_family_code="welding")
        job = _coords_job(canonical_job_family_code="manufacturing")  # ~9 mi
        r = compute_match(app, job, _make_employer(), _default_config(), _TODAY)
        assert r.match_tier == "adjacent"
        assert "near you" in (r.tier_reason or "")
