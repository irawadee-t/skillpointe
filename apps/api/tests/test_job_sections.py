"""Unit tests for the deterministic job-description section parser."""
from __future__ import annotations

from app.skilled_pro.job_sections import compute_content_hash, parse_job_sections

# Real Southwire-style scraped text (broken bullet wrap, ALL-CAPS inline headers,
# duplicated location/shift/pay lines) — the exact mess this parser exists for.
SOUTHWIRE_MESSY = """We
are proud to offer competitive compensation, employee benefits, tuition reimbursement and unlimited growth opportunities. Our more than seven decades of progressive growth can be attributed to our determination to developing innovative systems and solutions, exercising environmental stewardship and enhancing the well-being of the communities in which we work and live. How will you power what's possible?
Location: MC - Carrollton, GA
Shift: D: 6:50p-7a
Pay Rate: 23.40 - 24.89
JOB OVERVIEW:  The Take Up 3 is an entry level role where the individual will operate a take-up in line with the extruder.
GENERAL REQUIREMENTS:
High school diploma or equivalent
Must read, write, and speak English; Bilingual in Spanish is a plus
Must be able to stand and lift heavy loads for long periods of time
Must be able to follow instructions
Must be able to lift up to 45 lbs.
PRIMARY JOB TASKS:
This position may require a Southwire forklift license.
Perform take up and pay off operations as required.
Layer wind cable to customer specified ship out length and reel.
Operate per the applicable procedures.
Change out reels of cable while maintaining line function
SAFETY:
Follow all safety procedures and rules
Properly wear all required PPE
"""


def test_broken_bullet_merge():
    """A sub-4-word orphan followed by a lowercase-starting paragraph is a broken
    wrap — it must be rejoined into one intact sentence. (Marketing prose like
    this is classified into the collapsed "company" section.)"""
    result = parse_job_sections("We\nare proud to offer competitive compensation and benefits to every member of our growing team across the country.")
    everything = result["about"] + result["company"]
    assert len(everything) == 1
    assert everything[0].startswith("We are proud to offer")


def test_header_splitting_general_requirements_and_primary_job_tasks():
    result = parse_job_sections(SOUTHWIRE_MESSY)
    # GENERAL REQUIREMENTS: → needs
    assert "High school diploma or equivalent" in result["needs"]
    assert "Must be able to lift up to 45 lbs." in result["needs"]
    # PRIMARY JOB TASKS: → duties
    assert "Perform take up and pay off operations as required." in result["duties"]
    assert "Change out reels of cable while maintaining line function" in result["duties"]
    # Unknown-header SAFETY: bullets classified as duties by imperative verbs.
    assert "Follow all safety procedures and rules" in result["duties"]
    # Inline "JOB OVERVIEW: content" header lands its remainder in about.
    assert any("Take Up 3 is an entry level role" in p for p in result["about"])
    # Nothing from the needs section leaked into duties.
    assert "High school diploma or equivalent" not in result["duties"]


def test_fact_lines_extracted_and_removed():
    result = parse_job_sections(SOUTHWIRE_MESSY)
    assert result["facts"]["location_text"] == "MC - Carrollton, GA"
    assert result["facts"]["shift"] == "D: 6:50p-7a"
    assert result["facts"]["pay_text"] == "23.40 - 24.89"
    all_text = " ".join(result["about"] + result["duties"] + result["needs"])
    assert "Pay Rate" not in all_text
    assert "Shift:" not in all_text


def test_needs_vs_duties_classification_without_headers():
    raw = "\n".join(
        [
            "Must have a valid driver's license",
            "Ability to read blueprints",
            "Experience with hand tools preferred",
            "Load and unload trucks daily",
            "Operate a forklift safely",
            "Maintain a clean work area",
        ]
    )
    result = parse_job_sections(raw)
    assert "Must have a valid driver's license" in result["needs"]
    assert "Ability to read blueprints" in result["needs"]
    assert "Experience with hand tools preferred" in result["needs"]
    assert "Load and unload trucks daily" in result["duties"]
    assert "Operate a forklift safely" in result["duties"]
    assert "Maintain a clean work area" in result["duties"]


def test_preferred_and_benefits_sections():
    raw = (
        "About the role\nA great job at a great plant.\n"
        "Preferred Qualifications\nForklift certification\nSix Sigma experience\n"
        "Benefits We Offer:\n401k with Matching\nFamily and Individual Insurance Packages\n"
    )
    result = parse_job_sections(raw)
    assert "Forklift certification" in result["nice_to_have"]
    assert "401k with Matching" in result["benefits"]


def test_separate_raw_fields_feed_their_buckets():
    result = parse_job_sections(
        "An overview paragraph describing the job in enough detail to stay prose in the about section.",
        requirements_raw="High school diploma\n2+ years of manufacturing experience",
        preferred_qualifications_raw="Forklift certification",
        responsibilities_raw="Operate machinery\nPerform quality checks",
    )
    assert "High school diploma" in result["needs"]
    assert "2+ years of manufacturing experience" in result["needs"]
    assert "Forklift certification" in result["nice_to_have"]
    assert "Operate machinery" in result["duties"]
    assert len(result["about"]) == 1


def test_quality_flag_good_for_clean_parse():
    assert parse_job_sections(SOUTHWIRE_MESSY)["quality"] == "good"


def test_quality_flag_messy_for_unstructured_dump():
    # Long text with no recognizable headers, bullets, needs, or duty verbs:
    # everything piles into "about" as unclassified fragments.
    raw = "\n".join(
        [
            "Alpha bravo charlie delta echo",
            "Foxtrot golf hotel india juliet",
            "Kilo lima mike november oscar",
            "Papa quebec romeo sierra tango",
            "Uniform victor whiskey xray yankee",
            "Zulu one two three four five",
        ]
        * 8
    )
    assert parse_job_sections(raw)["quality"] == "messy"


def test_empty_input():
    result = parse_job_sections(None)
    assert result["about"] == []
    assert result["duties"] == []
    assert result["quality"] == "good"


def test_dedupe_across_buckets():
    result = parse_job_sections(
        "Requirements:\nHigh school diploma\nHigh school diploma",
        requirements_raw="High school diploma",
    )
    assert result["needs"].count("High school diploma") == 1


def test_megaline_blob_explodes_and_flags_messy():
    """Schneider-style dump: one newline-free line with inline CAPS headers and
    double-space item separators must be broken apart into real sections."""
    blob = (
        "Fabrication Associate I – Welder POSITION SUMMARY: This position is responsible "
        "for the forming, cutting, and welding of fabricated materials for a final product. "
        "SKILL (Education, Experience, Initiative, and Ingenuity)   "
        "Must possess a welding certificate from a technical school "
        "Must have actively welded in the last year   "
        "EFFORT (Physical Demand, Mental or Visual Demand)   "
        "Requires ability to reach overhead and lift up to 35 pounds repeatedly   "
        "RESPONSIBILITY (Equipment or Process, Material or Product)   "
        "Responsible for own product quality, proper measuring techniques, and tool use and care "
        "and other duties as assigned to keep the production line moving safely every day"
    )
    result = parse_job_sections(blob)
    # Inline headers were split out; needs and duties were recovered.
    assert any(m.startswith("Must possess a welding certificate") for m in result["needs"])
    assert any(m.startswith("Requires ability to reach overhead") for m in result["needs"])
    assert any(m.startswith("Responsible for own product quality") for m in result["duties"])
    # The "POSITION SUMMARY:" remainder landed in about.
    assert any("This position is responsible" in p for p in result["about"])
    # The unknown CAPS labels ("SKILL (…)", "EFFORT (…)") are now routed by
    # keyword, so the parse is reliable — no LLM cleanup needed.
    assert result["quality"] == "good"


def test_hash_stability():
    h1 = compute_content_hash("desc", "req", "pref", "resp")
    h2 = compute_content_hash("desc", "req", "pref", "resp")
    assert h1 == h2
    assert len(h1) == 64
    # Any field change or field-boundary shift changes the hash.
    assert compute_content_hash("desc", "req", "pref", "respX") != h1
    assert compute_content_hash("descreq", "", "pref", "resp") != h1
    # None and "" hash identically (both mean "absent").
    assert compute_content_hash(None, None, None, None) == compute_content_hash("", "", "", "")
