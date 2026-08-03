"""
test_geo_radius.py — applicant work-radius matching (pure, no DB).

Covers:
  - matching.geo.haversine_miles against known city-pair geodesic distances
  - geography gate truth table, incl. the "radius circle covers the job's
    city" case that motivated the feature
  - missing-coords fallback to state/region logic (backward compatible)
  - distance-graded geography_alignment scoring monotonicity
  - explanation text mentions distance in real terms
"""
import sys
from pathlib import Path

import pytest

# Allow importing from packages/matching
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "packages"))

from matching.config import NullHandlingConfig
from matching.gates import FAIL, NEAR_FIT, PASS, evaluate_geography_gate
from matching.geo import (
    DEFAULT_COMMUTE_RADIUS_MILES,
    effective_radius_miles,
    haversine_miles,
)
from matching.scorer import score_geography_alignment

# City centroids used across the tests
AUSTIN = (30.2672, -97.7431)        # Austin, TX
ROUND_ROCK = (30.5083, -97.6789)    # ~17 mi from Austin
SAN_ANTONIO = (29.4241, -98.4936)   # ~74 mi from Austin
NYC = (40.7128, -74.0060)
LA = (34.0522, -118.2437)
CHICAGO = (41.8781, -87.6298)
HOUSTON = (29.7604, -95.3698)


# ---------------------------------------------------------------------------
# Haversine correctness — known geodesic city-pair distances, +/- 1%
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("a, b, expected_miles", [
    (NYC, LA, 2445.6),        # New York -> Los Angeles
    (CHICAGO, HOUSTON, 940.0),  # Chicago -> Houston
    (AUSTIN, SAN_ANTONIO, 73.6),  # Austin -> San Antonio
])
def test_haversine_known_city_pairs(a, b, expected_miles):
    got = haversine_miles(a[0], a[1], b[0], b[1])
    assert got == pytest.approx(expected_miles, rel=0.01)


def test_haversine_zero_distance():
    assert haversine_miles(*AUSTIN, *AUSTIN) == pytest.approx(0.0, abs=1e-9)


def test_haversine_symmetry():
    assert haversine_miles(*AUSTIN, *SAN_ANTONIO) == pytest.approx(
        haversine_miles(*SAN_ANTONIO, *AUSTIN)
    )


def test_effective_radius_default():
    assert effective_radius_miles(None) == DEFAULT_COMMUTE_RADIUS_MILES
    assert effective_radius_miles(0) == DEFAULT_COMMUTE_RADIUS_MILES
    assert effective_radius_miles(25) == 25.0


# ---------------------------------------------------------------------------
# Geography gate truth table (with coordinates)
# ---------------------------------------------------------------------------

def _gate(*, radius=None, a=AUSTIN, j=ROUND_ROCK, a_city="Austin", j_city="Round Rock",
          a_state="TX", j_state="TX", relocate=False, reloc_states=None,
          work_setting="on_site", a_lat=None, j_lat=None, **kw):
    a_coords = a if a_lat is None else (a_lat, kw.get("a_lng"))
    j_coords = j if j_lat is None else (j_lat, kw.get("j_lng"))
    return evaluate_geography_gate(
        a_state, "south", relocate, False,
        j_state, "south", work_setting,
        relocation_states=reloc_states,
        applicant_lat=a_coords[0] if a_coords else None,
        applicant_lng=a_coords[1] if a_coords else None,
        job_lat=j_coords[0] if j_coords else None,
        job_lng=j_coords[1] if j_coords else None,
        commute_radius_miles=radius,
        applicant_city=a_city,
        job_city=j_city,
    )


def test_gate_radius_covers_job_city_passes():
    """The core case: job posted in Round Rock (~17 mi away); the applicant's
    25-mile radius circle covers that city, so the job is in range."""
    g = _gate(radius=25)
    assert g.result == PASS
    assert "mi" in g.reason and "25" in g.reason


def test_gate_small_radius_excludes_city():
    """Same job (~17 mi away), radius 15 -> just beyond (within 1.5x radius)
    is a near-fit; radius 10 -> well beyond (>1.5x) is a hard fail."""
    near = _gate(radius=15)
    assert near.result == NEAR_FIT
    assert "beyond" in near.reason

    far = _gate(radius=10)
    assert far.result == FAIL
    assert far.severity == "critical"


def test_gate_far_city_fails_without_relocation():
    """San Antonio (~74 mi) with a 25-mile radius and no relocation
    willingness is a critical geography failure that caps the score."""
    g = _gate(radius=25, j=SAN_ANTONIO, j_city="San Antonio")
    assert g.result == FAIL
    assert g.severity == "critical"
    assert "radius" in g.reason


def test_gate_same_city_always_passes():
    g = _gate(radius=10, j=AUSTIN, j_city="Austin")
    assert g.result == PASS
    assert "your city" in g.reason


def test_gate_relocation_state_overrides_radius():
    """Beyond the radius but the job's state is a chosen relocation state."""
    g = _gate(radius=25, j=CHICAGO, j_city="Chicago", j_state="IL",
              relocate=True, reloc_states=["IL", "WI"])
    assert g.result == PASS
    assert "relocation state" in g.reason


def test_gate_willing_to_relocate_no_state_list_passes():
    g = _gate(radius=25, j=CHICAGO, j_city="Chicago", j_state="IL", relocate=True)
    assert g.result == PASS
    assert "relocat" in g.reason


def test_gate_far_city_wrong_relocation_state_fails():
    g = _gate(radius=25, j=CHICAGO, j_city="Chicago", j_state="IL",
              relocate=True, reloc_states=["FL"])
    # IL is not in the chosen list; willing_to_relocate with a list means
    # "these states only" — near-fit at best via relocation prefs, never PASS.
    assert g.result in (NEAR_FIT, FAIL)
    assert g.result != PASS


def test_gate_remote_job_ignores_distance():
    g = _gate(radius=10, j=LA, j_city="Los Angeles", j_state="CA",
              work_setting="remote")
    assert g.result == PASS


def test_gate_widening_radius_flips_result():
    """The user story: changing the radius must change gating."""
    near = _gate(radius=10, j=SAN_ANTONIO, j_city="San Antonio")  # 74 mi
    wide = _gate(radius=100, j=SAN_ANTONIO, j_city="San Antonio")
    assert near.result == FAIL
    assert wide.result == PASS


# ---------------------------------------------------------------------------
# Missing-coords fallback — state/region logic, never hard-fails on absent data
# ---------------------------------------------------------------------------

def test_gate_missing_job_coords_falls_back_to_state():
    g = evaluate_geography_gate(
        "TX", "south", False, False, "TX", "south", "on_site",
        applicant_lat=AUSTIN[0], applicant_lng=AUSTIN[1],
        job_lat=None, job_lng=None,
        commute_radius_miles=10, applicant_city="Austin", job_city="El Paso",
    )
    assert g.result == PASS          # same state — legacy rule
    assert "same state" in g.reason


def test_gate_missing_applicant_coords_falls_back():
    g = evaluate_geography_gate(
        "TX", "south", False, False, "TX", "south", "on_site",
        applicant_lat=None, applicant_lng=None,
        job_lat=ROUND_ROCK[0], job_lng=ROUND_ROCK[1],
        commute_radius_miles=25,
    )
    assert g.result == PASS


# ---------------------------------------------------------------------------
# Distance-graded scoring — deterministic + monotone
# ---------------------------------------------------------------------------

def _score(dist_miles_coords, *, radius=25, relocate=False, reloc_states=None,
           j_state="TX"):
    return score_geography_alignment(
        "TX", "south", relocate, False, j_state, "south", "on_site",
        20.0, NullHandlingConfig(),
        relocation_states=reloc_states,
        applicant_lat=AUSTIN[0], applicant_lng=AUSTIN[1],
        job_lat=dist_miles_coords[0], job_lng=dist_miles_coords[1],
        commute_radius_miles=radius,
        applicant_city="Austin",
    )


def test_score_same_city_full_points():
    s = _score(AUSTIN)
    assert s.raw_score == 100.0


def test_score_monotone_nonincreasing_with_distance():
    # Points progressively farther east of Austin along the same latitude.
    lngs = [-97.74, -97.6, -97.4, -97.1, -96.5, -95.5, -94.0, -90.0]
    scores = [_score((AUSTIN[0], lng)).raw_score for lng in lngs]
    assert all(a >= b for a, b in zip(scores, scores[1:])), scores


def test_score_inside_radius_at_least_70():
    s = _score(ROUND_ROCK, radius=25)   # ~17 mi
    assert 70.0 <= s.raw_score < 100.0
    assert "inside your 25 mi radius" in s.rationale


def test_score_beyond_radius_relocator_floor_beats_stayer():
    stay = _score(SAN_ANTONIO, radius=25)                 # ~74 mi, no relocation
    move = _score(SAN_ANTONIO, radius=25, relocate=True)  # open to relocating
    assert move.raw_score >= 55.0
    assert stay.raw_score < move.raw_score
    assert stay.raw_score >= 20.0
    assert "beyond your 25 mi radius" in stay.rationale


def test_score_missing_coords_uses_legacy_logic():
    s = score_geography_alignment(
        "TX", "south", False, False, "TX", "south", "on_site",
        20.0, NullHandlingConfig(),
        commute_radius_miles=10,
    )
    assert s.raw_score == 100.0   # same state — legacy rule unchanged


# ---------------------------------------------------------------------------
# End-to-end: explanation text carries real distances, and radius changes
# flip eligibility through the whole engine
# ---------------------------------------------------------------------------

def test_engine_radius_change_flips_eligibility_and_explains_distance():
    from datetime import date

    from matching.config import load_config
    from matching.engine import compute_match

    config = load_config()
    job = {
        "id": "00000000-0000-0000-0000-00000000000b",
        "canonical_job_family_code": "electrical",
        "city": "San Antonio", "state": "TX", "region": "south",
        "lat": SAN_ANTONIO[0], "lng": SAN_ANTONIO[1],
        "work_setting": "on_site", "description_raw": "Electrician role.",
        "required_credentials": [], "pay_min": 25, "pay_max": 30,
        "pay_type": "hourly", "experience_level": "entry",
    }
    applicant_base = {
        "id": "00000000-0000-0000-0000-00000000000a",
        "canonical_job_family_code": "electrical",
        "city": "Austin", "state": "TX", "region": "south",
        "lat": AUSTIN[0], "lng": AUSTIN[1],
        "willing_to_relocate": False, "willing_to_travel": False,
        "relocation_preference": "stay_current", "travel_preference": "no_travel",
        "program_name_raw": "Electrical Technology",
    }

    narrow = compute_match({**applicant_base, "commute_radius_miles": 25},
                           job, {}, config, today=date(2026, 7, 1))
    wide = compute_match({**applicant_base, "commute_radius_miles": 100},
                         job, {}, config, today=date(2026, 7, 1))

    assert narrow.eligibility_status == "ineligible"
    assert wide.eligibility_status == "eligible"
    assert wide.base_fit_score > narrow.base_fit_score

    # Gap text mentions the real distance and the radius
    geo_gaps = [g for g in narrow.top_gaps if "radius" in g]
    assert geo_gaps and "mi" in geo_gaps[0]

    # Strength text on the wide match mentions distance in real terms
    geo_strengths = [s for s in wide.top_strengths if "radius" in s]
    assert geo_strengths and "mi" in geo_strengths[0]
