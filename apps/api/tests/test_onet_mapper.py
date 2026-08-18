"""
test_onet_mapper.py — Unit tests for scripts/map_onet.py (O*NET-SOC mapper).

Pure tests: the normalizer and tier logic run against a small in-memory
fixture index. Tests that need the downloaded O*NET text distribution
(audit/onet/db_*_text/) skip gracefully when the files are absent.

Run with:
  cd apps/api && pytest tests/test_onet_mapper.py -v
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from map_onet import (  # noqa: E402
    AUDIT_DIR,
    OnetIndex,
    find_onet_dir,
    load_onet_index,
    match_title,
    normalize_title,
    segment_candidates,
    stem_token,
)


# ---------------------------------------------------------------------------
# normalize_title
# ---------------------------------------------------------------------------

class TestNormalizeTitle:
    def test_lowercases_and_strips_punctuation(self):
        assert normalize_title("CNC/EDM Machine Operator") == "cnc edm machine operator"

    def test_strips_seniority_prefixes(self):
        assert normalize_title("Senior Electrician") == "electrician"
        assert normalize_title("Sr. Field Service Technician") == "field service technician"
        assert normalize_title("Jr Welder") == "welder"
        assert normalize_title("Lead CNC Programmer") == "cnc programmer"

    def test_strips_roman_numeral_level_suffixes(self):
        assert normalize_title("Materials Associate II") == "materials associate"
        assert normalize_title("Extruder Operator I") == "extruder operator"
        assert normalize_title("Machinist III") == "machinist"

    def test_strips_level_word_forms(self):
        assert normalize_title("Technician Level 2") == "technician"
        assert normalize_title("Technician Level III") == "technician"

    def test_strips_shift_noise(self):
        assert normalize_title("HVAC Installer - 2nd Shift") == "hvac installer"
        assert normalize_title("Test Technician -2nd shift") == "test technician"
        assert normalize_title("Quality Technician - Night Shift") == "quality technician"
        assert normalize_title("Weekend Welder") == "welder"

    def test_strips_employment_type_noise(self):
        assert normalize_title("Part-Time Material Handler") == "material handler"
        assert normalize_title("Nurse PRN") == "nurse"
        assert normalize_title("Entry Level - Industrial Plumber") == "industrial plumber"
        assert normalize_title("TIG Welder-Entry") == "tig welder"

    def test_collapses_whitespace(self):
        assert normalize_title("  Diesel   Mechanic  ") == "diesel mechanic"

    def test_keeps_meaningful_short_tokens(self):
        # hvac/cnc/edm are content, not noise
        assert "hvac" in normalize_title("HVAC Technician")
        assert normalize_title("CNC Machinist") == "cnc machinist"


class TestStemToken:
    def test_depluralizes(self):
        assert stem_token("electricians") == "electrician"
        assert stem_token("machinists") == "machinist"

    def test_preserves_short_and_ss_tokens(self):
        assert stem_token("gas") == "gas"
        assert stem_token("bus") == "bus"
        assert stem_token("press") == "press"

    def test_ies_plural(self):
        assert stem_token("assemblies") == "assembly"


class TestSegmentCandidates:
    def test_drops_location_suffix(self):
        cands = segment_candidates("Millwright - Louisville, KY")
        assert "millwright" in cands

    def test_drops_leading_qualifier(self):
        cands = segment_candidates(
            "Skilled Trade - Plumber Pipefitter - Kansas City Assembly Plant")
        assert "plumber pipefitter" in cands

    def test_splits_space_adjacent_hyphen_only(self):
        # "-TX" splits (space before hyphen); "Electro-Mechanical" must not
        cands = segment_candidates("Wind Hub Technician -TX 12 (Lubbock, TX)")
        assert "wind hub technician" in cands
        assert segment_candidates("Electro-Mechanical Technician") == [] or \
            all("electro mechanical" in c or "electro" not in c
                for c in segment_candidates("Electro-Mechanical Technician"))

    def test_single_segment_title_yields_no_candidates(self):
        assert segment_candidates("Electrician") == []


# ---------------------------------------------------------------------------
# Tier logic against a small fixture index
# ---------------------------------------------------------------------------

@pytest.fixture()
def fixture_index() -> OnetIndex:
    idx = OnetIndex()
    # Primary occupation titles (plural, like the real file)
    primaries = [
        ("47-2111.00", "Electricians"),
        ("51-4041.00", "Machinists"),
        ("47-2152.00", "Plumbers, Pipefitters, and Steamfitters"),
        ("49-9081.00", "Wind Turbine Service Technicians"),
        ("43-4051.00", "Customer Service Representatives"),
        ("49-9043.00", "Maintenance Workers, Machinery"),
        ("53-7062.00", "Laborers and Freight, Stock, and Material Movers, Hand"),
        ("47-4051.00", "Highway Maintenance Workers"),
    ]
    for soc, title in primaries:
        idx.soc_titles[soc] = title
        idx.add_title(soc, title, primary=True)
    # Alternate titles, including ambiguous ones under multiple SOCs
    alts = [
        ("47-2111.00", "Journeyman Electrician"),
        ("49-9043.00", "Machinist"),          # ambiguous alt
        ("51-4041.00", "Machinist"),          # ambiguous alt
        ("47-4051.00", "Material Handler"),   # ambiguous alt
        ("53-7062.00", "Material Handler"),   # ambiguous alt
        ("47-2152.00", "Pipefitter"),
        ("49-9081.00", "Wind Technician"),
    ]
    for soc, title in alts:
        idx.add_title(soc, title, primary=False)
    idx.job_zones = {"47-2111.00": "3", "51-4041.00": "3"}
    idx.finalize()
    return idx


class TestTierLogic:
    def test_exact_match(self, fixture_index):
        soc, title, tier = match_title("Journeyman Electrician", fixture_index)
        assert (soc, tier) == ("47-2111.00", "exact")

    def test_exact_via_depluralized_primary(self, fixture_index):
        # "Electrician" only exists as plural primary "Electricians"
        soc, _, tier = match_title("Electrician", fixture_index)
        assert (soc, tier) == ("47-2111.00", "exact")

    def test_exact_strips_seniority_and_level(self, fixture_index):
        soc, _, tier = match_title("Senior Machinist II", fixture_index)
        assert soc == "51-4041.00"
        assert tier == "exact"

    def test_ambiguous_alt_prefers_primary_title_owner(self, fixture_index):
        # "Machinist" is an alt under 49-9043 AND 51-4041; the stemmed
        # primary "Machinists" (51-4041) must win over the alt entries.
        soc, _, _ = match_title("Machinist", fixture_index)
        assert soc == "51-4041.00"

    def test_ambiguous_alt_resolves_by_primary_token_overlap(self, fixture_index):
        # "Material Handler" is an alt under 47-4051 (Highway Maintenance
        # Workers — no token overlap) and 53-7062 (…Material Movers, Hand —
        # shares "material"). Containment rule must pick 53-7062.
        soc, _, tier = match_title("Material Handler", fixture_index)
        assert (soc, tier) == ("53-7062.00", "exact")

    def test_segment_match_drops_qualifiers(self, fixture_index):
        soc, _, tier = match_title(
            "Skilled Trade - Journeyman Electrician - Cleveland Engine Plant",
            fixture_index)
        assert (soc, tier) == ("47-2111.00", "segment")

    def test_fuzzy_match_flagged_lower_confidence(self, fixture_index):
        # {wind, hub, technician} vs alt "Wind Technician" {wind, technician}
        # → Jaccard 2/3 >= 0.6, no exact/segment hit
        soc, matched, tier = match_title("Wind Hub Technician", fixture_index)
        assert (soc, tier) == ("49-9081.00", "fuzzy")
        assert matched == "Wind Technician"

    def test_fuzzy_below_threshold_is_unmapped(self, fixture_index):
        soc, matched, tier = match_title("Underwater Basket Weaver", fixture_index)
        assert (soc, matched, tier) == (None, None, "unmapped")

    def test_fuzzy_retries_on_segments(self, fixture_index):
        # Full title diluted by location tokens; segment "Wind Hub
        # Technician" still fuzzes to Wind Technician.
        soc, _, tier = match_title(
            "Wind Hub Technician - TX 16 (Hereford, TX area)", fixture_index)
        assert (soc, tier) == ("49-9081.00", "fuzzy")

    def test_deterministic(self, fixture_index):
        results = {match_title("Machinist", fixture_index) for _ in range(5)}
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Real data files (skip gracefully when not downloaded)
# ---------------------------------------------------------------------------

def _onet_dir_or_none():
    try:
        return find_onet_dir(None)
    except FileNotFoundError:
        return None


_ONET_DIR = _onet_dir_or_none()


@pytest.mark.skipif(_ONET_DIR is None,
                    reason=f"O*NET text files not downloaded under {AUDIT_DIR}")
class TestRealOnetData:
    def test_index_loads_with_sane_counts(self):
        idx = load_onet_index(_ONET_DIR)
        assert len(idx.soc_titles) > 900          # ~1,016 occupations
        assert len(idx._fuzzy) > 50_000           # ~57k alternate titles
        assert len(idx.job_zones) > 800

    def test_known_trades_map_correctly(self):
        idx = load_onet_index(_ONET_DIR)
        assert match_title("Electrician", idx)[0] == "47-2111.00"
        assert match_title("Machinist - First Shift", idx)[0] == "51-4041.00"
        # "HVAC Technician" is an alt title under several 49-9xxx codes
        # (49-9021 HVAC Mechanics, 49-9099.01 Geothermal Technicians); the
        # audit relies on the SOC major group, so assert at that level.
        assert match_title("HVAC Technician", idx)[0].startswith("49-9")
