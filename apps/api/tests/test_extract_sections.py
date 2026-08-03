"""Tests for the job-description post-processor against real scraped text."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))
from scraper.extract import parse_sections  # noqa: E402

SOUTHWIRE_REAL = """Manager, Engineering & Maintenance
Apply now »
Date:
Jun 29, 2026
Location:
Florence, AL, US, 35630
Company:
Southwire Company LLC
A leader in technology and innovation, Southwire Company, LLC is one of North America's largest wire and cable producers.
Location: Florence, AL
Job Summary
The Engineering and Maintenance Manager will provide daily leadership and long-term vision to the Engineering and Maintenance departments for the Southwire Florence Plant. This position is responsible for hands-on development, implementation and measurement of critical engineering processes and programs.
Required Education & Experience
Bachelor's degree in engineering.
Minimum 10 years of relevant engineering experience.
Must have prior experience in a manufacturing environment.
Must possess strong leadership skills as well as excellent communication and interpersonal skills.
Preferred Education & Experience
Bachelors degree in industrial, mechanical or electrical engineering.
Six Sigma experience, preferably Green or Black Belt.
Competencies
Attracts Top Talent
Drives Results
Benefits We Offer:
401k with Matching
Family and Individual Insurance Packages
Equal Employment Opportunity
Southwire is an equal opportunity employer.
"""

SCHNEIDER_LIKE = """About the role
You will support our manufacturing operations as a Production Technician.
What you'll do
- Operate machinery
- Perform quality checks
- Maintain a safe environment
Required qualifications
- High school diploma
- 2+ years of manufacturing experience
Preferred qualifications
- Forklift certification
Compensation
$22.00 - $26.50 per hour
"""


def test_southwire_real_description_splits_into_4_buckets():
    p = parse_sections(SOUTHWIRE_REAL)
    # The lead summary survives in description.
    assert p.description and "Engineering and Maintenance Manager" in p.description
    # Required section captured.
    assert p.requirements and "10 years" in p.requirements
    assert "manufacturing environment" in p.requirements
    # Preferred section captured separately.
    assert p.qualifications and "Six Sigma" in p.qualifications
    # Boilerplate dropped — none of the buckets carry the EEO line.
    haystack = " ".join(filter(None, [p.description, p.requirements, p.qualifications]))
    assert "equal opportunity" not in haystack.lower()


def test_extracts_years_of_experience_as_senior():
    p = parse_sections(SOUTHWIRE_REAL)
    assert p.experience_level == "senior"   # 10 years → senior


def test_schneider_style_splits_responsibilities():
    p = parse_sections(SCHNEIDER_LIKE)
    assert p.responsibilities and "Operate machinery" in p.responsibilities
    assert p.requirements and "2+ years" in p.requirements
    assert p.qualifications and "Forklift certification" in p.qualifications
    assert p.experience_level == "entry"    # "2+ years" → entry (<3)
    assert p.pay_raw and "22" in p.pay_raw and "26" in p.pay_raw


def test_empty_input_returns_all_none():
    p = parse_sections(None)
    assert (p.description, p.requirements, p.qualifications, p.responsibilities) == (None, None, None, None)
    p = parse_sections("   ")
    assert p.description is None


def test_no_section_headings_falls_into_description():
    text = "We are hiring a maintenance technician for our Carrollton, GA plant."
    p = parse_sections(text)
    assert p.description and "maintenance technician" in p.description
    assert p.requirements is None
    assert p.responsibilities is None
