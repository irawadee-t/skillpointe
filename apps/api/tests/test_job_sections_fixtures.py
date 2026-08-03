"""Fixture tests for the job-section parser against three REAL scraped jobs.

The fixtures are verbatim DB dumps of the exact jobs from the user-reported
screenshots (mid-word bullet snaps, fragmented pay, inline "·" walls, EEO
legalese mixed into requirements):

  * GE Vernova "Welder" (Chamblee, GA)   — snapped bullets + fragmented pay
  * Schneider "Maintenance Generalist"   — one unbroken wall with "·" separators
  * Ford "Skilled Trade - Welder General" — pay/benefits header + prose

Every assertion here encodes a display-quality invariant: no fragment bullets,
pay never fragmented, legalese quarantined in notices, and — critically — no
hallucination (output vocabulary ⊆ source vocabulary).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.skilled_pro.job_sections import SECTION_KEYS, parse_job_sections

_FIXTURES = Path(__file__).parent / "fixtures"

GE_ID = "70b54c60-5240-4fef-b307-c5057b4a8a81"
SCHNEIDER_ID = "1d179141-31e6-45b1-a88f-0fd8ced76149"
FORD_ID = "56c4a12c-5f60-4ba4-8101-4a69b6958cba"

_LIST_BUCKETS = ("duties", "needs", "nice_to_have", "benefits", "schedule")


def _load(job_id: str) -> tuple[dict, dict]:
    raw = json.loads((_FIXTURES / f"job_{job_id}.json").read_text())
    result = parse_job_sections(
        raw["description_raw"],
        raw["requirements_raw"],
        raw["preferred_qualifications_raw"],
        raw["responsibilities_raw"],
    )
    return raw, result


def _all_items(result: dict) -> list[str]:
    return [item for key in SECTION_KEYS for item in result[key]]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def _source_text(raw: dict) -> str:
    fields = (
        raw["description_raw"], raw["requirements_raw"],
        raw["preferred_qualifications_raw"], raw["responsibilities_raw"],
    )
    return " ".join(f or "" for f in fields)


@pytest.mark.parametrize("job_id", [GE_ID, SCHNEIDER_ID, FORD_ID])
def test_no_fragment_bullets(job_id):
    """No bullet starts lowercase or with punctuation — mid-word/mid-sentence
    snaps must have been rejoined."""
    _, result = _load(job_id)
    for item in _all_items(result):
        first = item[0]
        assert not first.islower(), f"bullet starts lowercase: {item!r}"
        assert first not in ",.;:)%", f"bullet starts with punctuation: {item!r}"


@pytest.mark.parametrize("job_id", [GE_ID, SCHNEIDER_ID, FORD_ID])
def test_no_dangling_fragment_bullets(job_id):
    """No bullet ends mid-sentence on a dangling word or open punctuation."""
    _, result = _load(job_id)
    dangling = {"a", "an", "the", "and", "or", "of", "to", "for", "with", "is", "are"}
    for key in _LIST_BUCKETS:
        for item in result[key]:
            assert not item.endswith((",", ";", "-", "–", "$", "&")), f"open fragment: {item!r}"
            last_word = re.split(r"[^A-Za-z']+", item.rstrip(".!?"))[-1].lower()
            assert last_word not in dangling, f"ends on dangling word: {item!r}"


@pytest.mark.parametrize("job_id", [GE_ID, SCHNEIDER_ID, FORD_ID])
def test_no_hallucination(job_id):
    """Output vocabulary ⊆ source vocabulary. The ONLY new tokens allowed are
    words formed by rejoining fragments the scraper snapped apart ("year"+"s"
    → "years"), which must appear in the whitespace-collapsed source."""
    raw, result = _load(job_id)
    src = _source_text(raw)
    src_tokens = _tokens(src)
    collapsed = re.sub(r"\s+", "", src.lower())
    out_text = " ".join(_all_items(result)) + " " + " ".join(
        v or "" for v in result["facts"].values()
    )
    for token in _tokens(out_text) - src_tokens:
        assert token in collapsed, f"hallucinated token: {token!r}"


# ---------------------------------------------------------------------------
# GE Vernova "Welder" — snapped bullets, fragmented pay, benefits legalese
# ---------------------------------------------------------------------------

def test_ge_snapped_requirement_reassembled():
    _, result = _load(GE_ID)
    assert any(
        item.startswith("At least 2 years of experience in welding") for item in result["needs"]
    ), result["needs"]
    # The fragments must not survive anywhere.
    for item in _all_items(result):
        assert item != "s"
        assert "2 year\n" not in item


def test_ge_pay_never_fragmented_and_captured_once():
    _, result = _load(GE_ID)
    # The fragmented "The pay for this position is $" / "27.68" / "per hour."
    # is reassembled and captured as the structured pay fact...
    assert result["facts"]["pay_text"] == "The pay for this position is $27.68 per hour"
    # ...and the amount appears nowhere else: exactly once across the payload.
    everything = " ".join(_all_items(result))
    assert "27.68" not in everything
    for item in _all_items(result):
        assert not item.endswith("$"), f"pay fragment bullet: {item!r}"
        assert item != "27.68"
        assert not item.startswith("per hour")


def test_ge_legalese_quarantined_in_notices():
    _, result = _load(GE_ID)
    notices = " ".join(result["notices"])
    assert "Equal Opportunity Employer" in notices
    assert "reserves the right to" in notices
    assert "drug screen" in notices
    # None of it pollutes the working sections.
    working = " ".join(result["needs"] + result["duties"] + result["about"] + result["benefits"])
    assert "Equal Opportunity Employer" not in working
    assert "reserves the right" not in working
    assert "without regard to" not in working


def test_ge_mission_prose_moved_to_company():
    _, result = _load(GE_ID)
    company = " ".join(result["company"])
    assert "climate crisis" in company
    about = " ".join(result["about"])
    assert "climate crisis" not in about
    assert "verdant" not in about
    # The actual role paragraph stays in about.
    assert "Welder C-Class position" in about


def test_ge_duties_not_snapped():
    _, result = _load(GE_ID)
    assert "Assist" not in result["duties"], "bare 'Assist' fragment bullet"
    assert any(
        item.startswith("Assist as needed with Generator field repair") for item in result["duties"]
    )


def test_ge_shift_prose_in_schedule():
    _, result = _load(GE_ID)
    schedule = " ".join(result["schedule"])
    assert "1st shift" in schedule
    assert "Monday-Friday" in schedule


def test_ge_benefits_have_real_content():
    _, result = _load(GE_ID)
    benefits = " ".join(result["benefits"])
    assert "Healthcare benefits include" in benefits
    assert "geographic differential" in benefits
    # Sponsor legalese does NOT belong under benefits.
    assert "Sponsor" not in benefits


# ---------------------------------------------------------------------------
# Schneider "Maintenance Generalist" — the unbroken wall of text
# ---------------------------------------------------------------------------

def test_schneider_wall_becomes_sections_with_real_bullets():
    _, result = _load(SCHNEIDER_ID)
    non_empty = [k for k in SECTION_KEYS if result[k]]
    assert len(non_empty) >= 3, non_empty
    # The inline "·" run was split into real duty bullets.
    assert len(result["duties"]) >= 10
    assert "Diagnose and correct machinery and equipment defects." in result["duties"]
    assert "Make repair parts." in result["duties"]
    # The "o"-separated course list became needs bullets.
    assert "Blueprint Reading" in result["needs"]
    assert "High school diploma or equivalency" in result["needs"]


def test_schneider_marketing_and_legal_separated():
    _, result = _load(SCHNEIDER_ID)
    company = " ".join(result["company"])
    assert "IMPACT" in company
    assert "global revenue" in company
    notices = " ".join(result["notices"])
    assert "Equal Opportunity Employer" in notices
    # About keeps only role-relevant prose.
    about = " ".join(result["about"])
    assert "Maintenance Generalist" in about
    assert "IMPACT" not in about
    assert "Equal Opportunity" not in about
    assert "global revenue" not in about


def test_schneider_shift_and_pay_extracted():
    _, result = _load(SCHNEIDER_ID)
    schedule = " ".join(result["schedule"])
    assert "1st Shift" in schedule
    assert "5:00am to 3:30pm" in schedule
    assert result["facts"]["pay_text"] is not None
    assert "$38.00/hour" in result["facts"]["pay_text"]


# ---------------------------------------------------------------------------
# Ford "Skilled Trade - Welder General" — thin but must stay clean
# ---------------------------------------------------------------------------

def test_ford_pay_prose_intact_in_benefits():
    _, result = _load(FORD_ID)
    benefits = " ".join(result["benefits"])
    # The premium/progression context adds info beyond the structured pay
    # figure, so the full sentence is kept — intact, in Pay & benefits.
    assert "top hourly base rate of $44.765" in benefits
    assert "holiday premiums" in benefits
    # The mangled header split ("Rate of" / "Pay and") must not occur.
    for item in _all_items(result):
        assert item not in ("Rate of", "Pay and", "Benefits:")


def test_ford_about_clean():
    _, result = _load(FORD_ID)
    assert result["about"] == [
        "This job posting is not location specific, it provides candidates to fill "
        "the openings throughout SE Michigan."
    ]


@pytest.mark.parametrize("job_id", [GE_ID, SCHNEIDER_ID, FORD_ID])
def test_quality_good_deterministically(job_id):
    """All three screenshot jobs must parse cleanly WITHOUT the LLM path."""
    _, result = _load(job_id)
    assert result["quality"] == "good"
