"""Evidence-weighted score aggregation + candidate adjacency expansion."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

from matching.scorer import DimensionScore  # noqa: E402
from matching import state_adjacency  # noqa: E402


class TestEvidenceRenormalization:
    """The structured score is the weighted mean over evidence-backed
    dimensions; defaults no longer dilute every list into a narrow band."""

    def _score(self, app_overrides=None, job_overrides=None):
        from matching.scorer import compute_structured_score
        from matching.config import load_config
        from matching.normalizer import TimingResult
        config = load_config()
        app = {
            "canonical_job_family_code": "hvac_r", "state": "GA",
            "region": "Southeast", "relocation_preference": "within_state",
        }
        app.update(app_overrides or {})
        job = {
            "canonical_job_family_code": "hvac_r", "state": "GA",
            "region": "Southeast", "work_setting": "onsite",
        }
        job.update(job_overrides or {})
        timing = TimingResult(None, "unknown", False)
        return compute_structured_score(app, job, timing, config)

    def test_returns_evidence_pct(self):
        _, dims, evidence = self._score()
        assert 0.0 <= evidence <= 100.0
        flagged = sum(d.weight for d in dims if d.null_handling_applied)
        total = sum(d.weight for d in dims)
        assert abs(evidence - 100.0 * (total - flagged) / total) < 0.11

    def test_defaults_do_not_dilute(self):
        # A same-family, same-state pair with unknown timing/comp/experience:
        # the known dimensions are strong, so the renormalized score must sit
        # near their level instead of being dragged to the default band.
        score, dims, evidence = self._score()
        known = [d for d in dims if not d.null_handling_applied]
        known_mean = sum(d.weight * d.raw_score for d in known) / sum(d.weight for d in known)
        assert abs(score - known_mean) < 0.51
        assert evidence < 100.0  # this profile really does have unknowns

    def test_more_evidence_never_flagged_as_less(self):
        _, _, sparse_ev = self._score()
        _, _, rich_ev = self._score(app_overrides={
            "experience_raw": "Completed a 6-month HVAC installation externship "
                              "with residential and light-commercial systems.",
            "has_internship": True,
        })
        assert rich_ev > sparse_ev

    def test_trade_school_fallback_is_flagged_default(self):
        from matching.scorer import score_experience_alignment
        d = score_experience_alignment(None, None, None, 10.0, 55.0)
        assert d.null_handling_applied is True
        assert d.raw_score == 55.0  # score unchanged; only honestly labeled


class TestStateAdjacency:
    def test_symmetric(self):
        for a, nbrs in state_adjacency.ADJACENT.items():
            for b in nbrs:
                assert a in state_adjacency.ADJACENT[b], f"{a}-{b} not symmetric"

    def test_border_metro_pairs(self):
        assert state_adjacency.is_adjacent("NJ", "PA")   # Camden -> Philadelphia
        assert state_adjacency.is_adjacent("KY", "OH")

    def test_not_adjacent(self):
        assert not state_adjacency.is_adjacent("GA", "TX")
        assert not state_adjacency.is_adjacent("CA", "TX")

    def test_four_corners_diagonals_excluded(self):
        assert not state_adjacency.is_adjacent("AZ", "CO")
        assert not state_adjacency.is_adjacent("NM", "UT")

    def test_unknowns_are_empty(self):
        assert state_adjacency.neighbors(None) == frozenset()
        assert state_adjacency.neighbors("AK") == frozenset()
        assert state_adjacency.neighbors("XX") == frozenset()

    def test_case_and_whitespace(self):
        assert "PA" in state_adjacency.neighbors(" nj ")


class TestLocationParsing:
    """Canadian postings must never acquire a US state (the ON/CA bug)."""

    def _parse(self, s):
        from scraper.base import parse_location
        return parse_location(s)

    def test_ontario_canada_is_not_california(self):
        assert self._parse("Whitby, ON, CA, L4K 4B5") == ("Whitby", None)
        assert self._parse("Vaughan, ON, CA, L4K 4B5") == ("Vaughan", None)

    def test_ontario_california_is_california(self):
        assert self._parse("Ontario, CA") == ("Ontario", "CA")

    def test_normal_us_forms(self):
        assert self._parse("Carrollton, GA, US, 30119") == ("Carrollton", "GA")
        assert self._parse("Phoenix, AZ") == ("Phoenix", "AZ")

    def test_province_only(self):
        assert self._parse("Oakville, ON") == ("Oakville", None)
