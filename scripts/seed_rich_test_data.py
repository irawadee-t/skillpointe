#!/usr/bin/env python3
"""
seed_rich_test_data.py — Populate richer test data for SkillPointe Match.

Must be run AFTER seed_test_users.py (which creates the auth users).

Creates:
  - Updated Jane Smith profile with essays, experience, career goals
  - 3 additional employers with diverse jobs (8 total jobs)
  - Pre-computed matches with a realistic mix of eligible / near_fit / ineligible
  - Full dimension-score breakdowns for each match

Usage:
    cd apps/api && source .venv/bin/activate
    python ../../scripts/seed_rich_test_data.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

env_file = Path(__file__).parent.parent / "apps" / "api" / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:54322/postgres",
)


# ── Employer data ──────────────────────────────────────────────

EMPLOYERS = [
    {
        "name": "Texas Welding Works",
        "industry": "Welding & Fabrication",
        "description": "Full-service welding shop specializing in structural steel and pipe welding for the energy sector.",
        "city": "Austin",
        "state": "TX",
        "region": "southwest",
        "is_partner": True,
    },
    {
        "name": "Lone Star Construction",
        "industry": "General Construction",
        "description": "Commercial and residential general contractor operating across central Texas.",
        "city": "San Antonio",
        "state": "TX",
        "region": "southwest",
        "is_partner": True,
    },
    {
        "name": "Capitol HVAC Services",
        "industry": "HVAC/Mechanical",
        "description": "Residential and commercial HVAC installation and maintenance.",
        "city": "Austin",
        "state": "TX",
        "region": "southwest",
        "is_partner": False,
    },
    {
        "name": "Gulf Coast Energy",
        "industry": "Energy / Oil & Gas",
        "description": "Midstream energy company with pipeline and facility welding needs across the Gulf Coast.",
        "city": "Houston",
        "state": "TX",
        "region": "southwest",
        "is_partner": True,
    },
]

# ── Job data (keyed by employer name) ──────────────────────────

JOBS = [
    # --- Texas Welding Works ---
    {
        "employer": "Texas Welding Works",
        "title_raw": "Entry-Level MIG/TIG Welder",
        "title_normalized": "MIG/TIG Welder",
        "family_code": "welding",
        "city": "Austin",
        "state": "TX",
        "region": "southwest",
        "work_setting": "on_site",
        "travel_requirement": "none",
        "pay_min": 21.00,
        "pay_max": 27.00,
        "pay_type": "hourly",
        "description_raw": (
            "Join our welding team working on structural steel projects for commercial clients. "
            "You will perform MIG and TIG welding on mild steel and aluminum. Training provided on "
            "specific processes. Great first role for recent welding program graduates."
        ),
        "requirements_raw": (
            "Completion of a welding technology program or equivalent. "
            "Basic knowledge of MIG and TIG processes. Ability to read blueprints. "
            "Must pass pre-employment weld test."
        ),
        "experience_level": "entry",
        "required_credentials": [],
        "preferred_credentials": ["AWS D1.1"],
    },
    {
        "employer": "Texas Welding Works",
        "title_raw": "Certified Pipe Welder",
        "title_normalized": "Pipe Welder",
        "family_code": "welding",
        "city": "Austin",
        "state": "TX",
        "region": "southwest",
        "work_setting": "on_site",
        "travel_requirement": "moderate",
        "pay_min": 32.00,
        "pay_max": 42.00,
        "pay_type": "hourly",
        "description_raw": (
            "Experienced pipe welder needed for energy sector projects. Work involves SMAW and "
            "GTAW processes on carbon steel and stainless pipe. Travel to client sites required."
        ),
        "requirements_raw": (
            "Minimum 3 years pipe welding experience. Active 6G certification required. "
            "ASME Section IX qualification preferred. Must hold valid driver's license. "
            "Willing to travel to job sites across central Texas."
        ),
        "experience_level": "mid",
        "required_credentials": ["6G Pipe Certification"],
        "preferred_credentials": ["ASME Section IX", "AWS D1.1"],
        "required_experience_years": 3,
    },
    # --- Acme Industrial (existing employer — we'll just add another job) ---
    {
        "employer": "Acme Industrial",
        "title_raw": "Welding Shop Helper",
        "title_normalized": "Shop Helper",
        "family_code": "welding",
        "city": "Austin",
        "state": "TX",
        "region": "southwest",
        "work_setting": "on_site",
        "travel_requirement": "none",
        "pay_min": 17.00,
        "pay_max": 21.00,
        "pay_type": "hourly",
        "description_raw": (
            "Assist welders in a busy fabrication shop. Duties include material preparation, "
            "grinding, fitting, and cleanup. Hands-on welding opportunities as skills develop. "
            "Great entry point for someone just out of a welding program."
        ),
        "requirements_raw": (
            "High school diploma or GED. Welding program coursework strongly preferred. "
            "No certification required — we train on the job."
        ),
        "experience_level": "entry",
        "required_credentials": [],
        "preferred_credentials": [],
    },
    # --- Lone Star Construction ---
    {
        "employer": "Lone Star Construction",
        "title_raw": "Structural Steel Welder",
        "title_normalized": "Structural Welder",
        "family_code": "welding",
        "city": "San Antonio",
        "state": "TX",
        "region": "southwest",
        "work_setting": "on_site",
        "travel_requirement": "light",
        "pay_min": 24.00,
        "pay_max": 32.00,
        "pay_type": "hourly",
        "description_raw": (
            "Perform structural welding on commercial construction sites. SMAW and FCAW processes. "
            "Must be comfortable working at heights and outdoors in Texas heat. "
            "We value safety and provide comprehensive PPE."
        ),
        "requirements_raw": (
            "Welding certificate or associate degree. AWS D1.1 Structural certification preferred. "
            "OSHA 10 preferred. Ability to lift 50 lbs and work at heights."
        ),
        "experience_level": "entry",
        "required_credentials": [],
        "preferred_credentials": ["AWS D1.1", "OSHA 10"],
    },
    {
        "employer": "Lone Star Construction",
        "title_raw": "General Construction Laborer",
        "title_normalized": "Construction Laborer",
        "family_code": "construction",
        "city": "San Antonio",
        "state": "TX",
        "region": "southwest",
        "work_setting": "on_site",
        "travel_requirement": "light",
        "pay_min": 16.00,
        "pay_max": 20.00,
        "pay_type": "hourly",
        "description_raw": (
            "General construction laborer needed for commercial build-outs. Duties include site "
            "cleanup, material handling, assisting tradespeople, and basic demolition."
        ),
        "requirements_raw": (
            "No formal trade certification required. Must be physically fit. "
            "Construction pre-apprenticeship program is a plus."
        ),
        "experience_level": "entry",
        "required_credentials": [],
        "preferred_credentials": [],
    },
    # --- Capitol HVAC Services ---
    {
        "employer": "Capitol HVAC Services",
        "title_raw": "HVAC Installation Technician",
        "title_normalized": "HVAC Install Tech",
        "family_code": "hvac",
        "city": "Austin",
        "state": "TX",
        "region": "southwest",
        "work_setting": "on_site",
        "travel_requirement": "moderate",
        "pay_min": 20.00,
        "pay_max": 28.00,
        "pay_type": "hourly",
        "description_raw": (
            "Install residential and light commercial HVAC systems. Work includes ductwork, "
            "refrigerant line sets, and thermostat wiring. Must have reliable transportation."
        ),
        "requirements_raw": (
            "HVAC certificate or apprenticeship completion required. "
            "EPA Section 608 certification required. Valid driver's license."
        ),
        "experience_level": "entry",
        "required_credentials": ["EPA Section 608"],
        "preferred_credentials": ["NATE"],
        "required_experience_years": 0,
    },
    # --- Gulf Coast Energy ---
    {
        "employer": "Gulf Coast Energy",
        "title_raw": "Pipeline Welder — Field",
        "title_normalized": "Pipeline Welder",
        "family_code": "welding",
        "city": "Houston",
        "state": "TX",
        "region": "southwest",
        "work_setting": "on_site",
        "travel_requirement": "frequent",
        "pay_min": 36.00,
        "pay_max": 50.00,
        "pay_type": "hourly",
        "description_raw": (
            "Field pipeline welder for midstream natural gas projects. "
            "Work is outdoors in various conditions across the Gulf Coast region. "
            "Excellent per diem and benefits package."
        ),
        "requirements_raw": (
            "Minimum 5 years pipeline welding experience. 6G certification on carbon and stainless. "
            "API 1104 qualification required. Must pass drug screen and background check. "
            "Must be willing to travel extensively."
        ),
        "experience_level": "senior",
        "required_credentials": ["6G Pipe Certification", "API 1104"],
        "preferred_credentials": ["ASME Section IX"],
        "required_experience_years": 5,
        "background_check_required": True,
        "drug_test_required": True,
    },
    {
        "employer": "Gulf Coast Energy",
        "title_raw": "Welder Helper / Apprentice",
        "title_normalized": "Welder Helper",
        "family_code": "welding",
        "city": "Houston",
        "state": "TX",
        "region": "southwest",
        "work_setting": "on_site",
        "travel_requirement": "moderate",
        "pay_min": 18.00,
        "pay_max": 23.00,
        "pay_type": "hourly",
        "description_raw": (
            "Assist certified welders on pipeline construction and maintenance. "
            "Grind, fit, and prep joints. Opportunity to progress into a welding role "
            "as skills develop. We invest in our apprentices."
        ),
        "requirements_raw": (
            "Welding program completion or current enrollment in final semester. "
            "No certification required. Must have reliable transportation and be "
            "willing to travel within the Houston metro area."
        ),
        "experience_level": "entry",
        "required_credentials": [],
        "preferred_credentials": [],
    },
]

# ── Pre-computed match data ────────────────────────────────────
# Keyed by (job title_raw).  Applicant is always Jane Smith.

MATCHES = [
    # Match 1 — strong eligible fit: entry MIG/TIG at Texas Welding Works
    {
        "job_title": "Entry-Level MIG/TIG Welder",
        "eligibility_status": "eligible",
        "base_fit_score": 82.3,
        "weighted_structured_score": 85.0,
        "semantic_score": 74.0,
        "policy_adjusted_score": 91.3,
        "match_label": "strong_fit",
        "top_strengths": [
            "Trade alignment: Welding Technology degree maps directly to MIG/TIG Welder role",
            "Geography: Austin TX — same city, no relocation needed",
            "Timing: Available June 2026, aligns with hiring window",
            "Education: Associate degree exceeds minimum requirement",
        ],
        "top_gaps": [
            "No documented professional welding experience yet (typical for new graduate)",
        ],
        "required_missing_items": [],
        "recommended_next_step": "Apply now — this is an excellent fit for your background. Prepare a portfolio of your welding coursework projects.",
        "confidence_level": "high",
        "hard_gate_rationale": {
            "job_family": {"result": "pass", "reason": "Welding Technology maps directly to welding job family"},
            "geography": {"result": "pass", "reason": "Austin TX matches job location exactly"},
            "timing_readiness": {"result": "pass", "reason": "Available June 2026, within employer's window"},
            "credential": {"result": "pass", "reason": "No hard credential required for entry level"},
            "explicit_minimum": {"result": "pass", "reason": "Welding program completion satisfies minimum requirements"},
        },
        "policy_modifiers": [
            {"policy": "partner_employer_preference", "value": 5, "reason": "Texas Welding Works is a SkillPointe partner"},
            {"policy": "readiness_preference", "value": 3, "reason": "Completing program within 3 months"},
            {"policy": "geography_preference", "value": 1, "reason": "Local — same city"},
        ],
        "dimension_scores": [
            ("trade_program_alignment", 25, 95, 23.75, "Welding Technology directly matches MIG/TIG Welder position", False),
            ("geography_alignment", 20, 98, 19.60, "Austin TX → Austin TX — same city, zero commute gap", False),
            ("credential_readiness", 15, 78, 11.70, "No credential required; associate degree exceeds minimum", False),
            ("timing_readiness", 10, 85, 8.50, "Available June 2026 — aligns with hiring window", False),
            ("experience_internship_alignment", 10, 55, 5.50, "200-hour shop internship provides relevant hands-on experience", True),
            ("industry_alignment", 5, 90, 4.50, "Welding shop — direct industry match", False),
            ("compensation_alignment", 5, 80, 4.00, "Pay range $21–$27/hr appropriate for entry level", False),
            ("work_style_signal_alignment", 5, 82, 4.10, "On-site role; applicant is local and hands-on oriented", False),
            ("employer_soft_pref_alignment", 5, 68, 3.40, "Blueprint reading mentioned; applicant has coursework exposure", False),
        ],
    },
    # Match 2 — eligible: Welding Shop Helper at Acme
    {
        "job_title": "Welding Shop Helper",
        "eligibility_status": "eligible",
        "base_fit_score": 78.5,
        "weighted_structured_score": 80.0,
        "semantic_score": 72.0,
        "policy_adjusted_score": 86.5,
        "match_label": "strong_fit",
        "top_strengths": [
            "Trade alignment: Welding program is ideal preparation for shop helper role",
            "Geography: Same city — Austin TX",
            "Low barrier: No certification required, training provided",
            "Good stepping stone: hands-on welding opportunities as skills develop",
        ],
        "top_gaps": [
            "Lower pay range than other welding positions ($17–$21/hr)",
        ],
        "required_missing_items": [],
        "recommended_next_step": "Apply — this role offers excellent hands-on training. Ask about their welder progression pathway during the interview.",
        "confidence_level": "high",
        "hard_gate_rationale": {
            "job_family": {"result": "pass", "reason": "Welding program maps to welding shop role"},
            "geography": {"result": "pass", "reason": "Same city — Austin TX"},
            "timing_readiness": {"result": "pass", "reason": "Available June 2026"},
            "credential": {"result": "pass", "reason": "No credential required"},
            "explicit_minimum": {"result": "pass", "reason": "Welding coursework satisfies preference"},
        },
        "policy_modifiers": [
            {"policy": "partner_employer_preference", "value": 5, "reason": "Acme Industrial is a SkillPointe partner"},
            {"policy": "readiness_preference", "value": 3, "reason": "Program completion within 3 months"},
        ],
        "dimension_scores": [
            ("trade_program_alignment", 25, 88, 22.00, "Welding coursework directly relevant to shop helper duties", False),
            ("geography_alignment", 20, 98, 19.60, "Austin TX → Austin TX — same city", False),
            ("credential_readiness", 15, 85, 12.75, "No credential required — low barrier to entry", False),
            ("timing_readiness", 10, 85, 8.50, "Available June 2026", False),
            ("experience_internship_alignment", 10, 50, 5.00, "Limited experience but role is designed for beginners", True),
            ("industry_alignment", 5, 88, 4.40, "Fabrication shop — direct industry match", False),
            ("compensation_alignment", 5, 60, 3.00, "Pay range $17–$21/hr — lower than market avg for welding", False),
            ("work_style_signal_alignment", 5, 80, 4.00, "On-site shop work matches applicant orientation", False),
            ("employer_soft_pref_alignment", 5, 55, 2.75, "No specific soft preferences stated", True),
        ],
    },
    # Match 3 — eligible: entry-level Welder at Acme (existing job, overwrite old match)
    {
        "job_title": "Welder — Entry Level",
        "eligibility_status": "eligible",
        "base_fit_score": 79.5,
        "weighted_structured_score": 81.0,
        "semantic_score": 74.0,
        "policy_adjusted_score": 87.5,
        "match_label": "strong_fit",
        "top_strengths": [
            "Trade alignment: Welding Technology maps directly to Welder job family",
            "Geography: Austin TX — same city as job location",
            "Timing: Available June 2026, within hiring window",
        ],
        "top_gaps": [
            "Experience: Limited documented internship hours",
        ],
        "required_missing_items": [
            "1 year of documented welding experience preferred (not required for entry level)",
        ],
        "recommended_next_step": "Apply directly — you meet all key requirements for this entry-level welding role.",
        "confidence_level": "high",
        "hard_gate_rationale": {
            "job_family": {"result": "pass", "reason": "Welding Technology aligns directly with Welder job family"},
            "geography": {"result": "pass", "reason": "Austin TX matches job location"},
            "timing_readiness": {"result": "pass", "reason": "Available from June 2026 — within window"},
            "credential": {"result": "pass", "reason": "No hard credential requirements for entry level"},
            "explicit_minimum": {"result": "pass", "reason": "No explicit minimum stated beyond trade program"},
        },
        "policy_modifiers": [
            {"policy": "partner_employer_preference", "value": 5, "reason": "Acme Industrial is a SkillPointe partner employer"},
            {"policy": "readiness_preference", "value": 3, "reason": "Applicant completing program in < 3 months"},
        ],
        "dimension_scores": [
            ("trade_program_alignment", 25, 90, 22.50, "Welding Technology maps directly to Welding & Metal Fabrication family", False),
            ("geography_alignment", 20, 96, 19.20, "Austin TX → Austin TX — same city", False),
            ("credential_readiness", 15, 72, 10.80, "No hard credentials required; completion date within window", False),
            ("timing_readiness", 10, 80, 8.00, "Available June 2026 — within acceptable hiring window", False),
            ("experience_internship_alignment", 10, 50, 5.00, "Limited documented experience — typical for program graduate", True),
            ("industry_alignment", 5, 85, 4.25, "Manufacturing/industrial sector aligns", False),
            ("compensation_alignment", 5, 75, 3.75, "Pay range $22–$28/hr consistent with entry-level expectations", False),
            ("work_style_signal_alignment", 5, 78, 3.90, "On-site role — applicant is local, no remote preference detected", False),
            ("employer_soft_pref_alignment", 5, 50, 2.50, "No soft preferences specified by employer", True),
        ],
    },
    # Match 4 — eligible: Structural Steel Welder at Lone Star
    {
        "job_title": "Structural Steel Welder",
        "eligibility_status": "eligible",
        "base_fit_score": 71.2,
        "weighted_structured_score": 74.0,
        "semantic_score": 62.0,
        "policy_adjusted_score": 79.2,
        "match_label": "good_fit",
        "top_strengths": [
            "Trade alignment: Welding Technology directly applicable to structural welding",
            "Geography: San Antonio is nearby — same region, short commute/relocation",
            "Applicant willing to relocate — San Antonio is feasible",
        ],
        "top_gaps": [
            "AWS D1.1 Structural certification preferred but not yet held",
            "Must be comfortable working at heights — not confirmed",
        ],
        "required_missing_items": [
            "AWS D1.1 certification — preferred, not required; can be obtained during employment",
        ],
        "recommended_next_step": "Strong option — apply and mention willingness to pursue AWS D1.1 during employment. Highlight any height-work experience.",
        "confidence_level": "high",
        "hard_gate_rationale": {
            "job_family": {"result": "pass", "reason": "Welding Technology aligns with structural welding"},
            "geography": {"result": "pass", "reason": "San Antonio TX is in same region; applicant willing to relocate"},
            "timing_readiness": {"result": "pass", "reason": "Available June 2026"},
            "credential": {"result": "pass", "reason": "No hard credential requirement; AWS D1.1 is preferred only"},
            "explicit_minimum": {"result": "pass", "reason": "Welding certificate or associate degree requirement met"},
        },
        "policy_modifiers": [
            {"policy": "partner_employer_preference", "value": 5, "reason": "Lone Star Construction is a SkillPointe partner"},
            {"policy": "readiness_preference", "value": 3, "reason": "Near completion"},
        ],
        "dimension_scores": [
            ("trade_program_alignment", 25, 85, 21.25, "Welding Technology relevant to structural steel welding", False),
            ("geography_alignment", 20, 72, 14.40, "San Antonio TX — same state/region, ~80 miles from Austin", False),
            ("credential_readiness", 15, 60, 9.00, "AWS D1.1 preferred but not held; associate degree meets base requirement", False),
            ("timing_readiness", 10, 85, 8.50, "Available June 2026 — within window", False),
            ("experience_internship_alignment", 10, 50, 5.00, "Limited experience — entry-level position accommodates this", True),
            ("industry_alignment", 5, 75, 3.75, "Construction sector — related but not identical to shop fabrication", False),
            ("compensation_alignment", 5, 85, 4.25, "Pay range $24–$32/hr — good for entry-level structural role", False),
            ("work_style_signal_alignment", 5, 65, 3.25, "On-site outdoor construction work — applicant orientation unknown", True),
            ("employer_soft_pref_alignment", 5, 55, 2.75, "OSHA 10 preferred; applicant does not hold it", True),
        ],
    },
    # Match 5 — eligible: Welder Helper at Gulf Coast Energy
    {
        "job_title": "Welder Helper / Apprentice",
        "eligibility_status": "eligible",
        "base_fit_score": 68.0,
        "weighted_structured_score": 70.0,
        "semantic_score": 60.0,
        "policy_adjusted_score": 76.0,
        "match_label": "good_fit",
        "top_strengths": [
            "Trade alignment: Welding program directly relevant to welder helper duties",
            "Career progression: Clear path from helper to certified welder",
            "Employer invests in apprentice development",
        ],
        "top_gaps": [
            "Location: Houston — requires relocation from Austin (applicant is willing)",
            "Travel within Houston metro area required",
        ],
        "required_missing_items": [],
        "recommended_next_step": "Good opportunity for career growth. Apply and discuss relocation timeline — employer may assist with housing.",
        "confidence_level": "medium",
        "hard_gate_rationale": {
            "job_family": {"result": "pass", "reason": "Welding program matches welder helper role"},
            "geography": {"result": "pass", "reason": "Houston TX — same state, applicant willing to relocate"},
            "timing_readiness": {"result": "pass", "reason": "Available June 2026 — program completion meets requirement"},
            "credential": {"result": "pass", "reason": "No certification required"},
            "explicit_minimum": {"result": "pass", "reason": "Program completion satisfies requirement"},
        },
        "policy_modifiers": [
            {"policy": "partner_employer_preference", "value": 5, "reason": "Gulf Coast Energy is a SkillPointe partner"},
            {"policy": "readiness_preference", "value": 3, "reason": "Near completion"},
        ],
        "dimension_scores": [
            ("trade_program_alignment", 25, 82, 20.50, "Welding program directly relevant to welder helper role", False),
            ("geography_alignment", 20, 55, 11.00, "Houston TX — same state but 165 miles; relocation needed", False),
            ("credential_readiness", 15, 80, 12.00, "No credential required", False),
            ("timing_readiness", 10, 85, 8.50, "Available June 2026", False),
            ("experience_internship_alignment", 10, 50, 5.00, "Entry-level role designed for learners", True),
            ("industry_alignment", 5, 70, 3.50, "Energy sector — industrial welding context", False),
            ("compensation_alignment", 5, 65, 3.25, "Pay $18–$23/hr — entry level for energy sector", False),
            ("work_style_signal_alignment", 5, 60, 3.00, "Field work with travel — applicant travel willingness unknown", True),
            ("employer_soft_pref_alignment", 5, 60, 3.00, "Reliable transportation needed; not confirmed", True),
        ],
    },
    # Match 6 — near_fit: Metal Fabricator at Acme (existing job)
    {
        "job_title": "Metal Fabricator — Mid Level",
        "eligibility_status": "near_fit",
        "base_fit_score": 48.4,
        "weighted_structured_score": 55.0,
        "semantic_score": 52.0,
        "policy_adjusted_score": 45.4,
        "match_label": "moderate_fit",
        "top_strengths": [
            "Trade background: Welding skills transfer to fabrication work",
            "Geography: Austin TX — same city",
        ],
        "top_gaps": [
            "Experience gap: 2 years fabrication experience required — applicant has limited hours",
            "Certification gap: AWS certification preferred but not held",
            "Mid-level role may be premature for new program graduate",
        ],
        "required_missing_items": [
            "Minimum 2 years fabrication experience (required)",
            "AWS certification (preferred)",
        ],
        "recommended_next_step": "Build 1–2 years of entry-level welding experience first, then pursue AWS certification. This role could be a good target in 18–24 months.",
        "confidence_level": "medium",
        "hard_gate_rationale": {
            "job_family": {"result": "pass", "reason": "Welding background adjacent to fabrication"},
            "geography": {"result": "pass", "reason": "Austin TX matches"},
            "timing_readiness": {"result": "pass", "reason": "Available June 2026"},
            "credential": {"result": "near_fit", "reason": "AWS certification preferred; applicant does not hold it", "severity": "moderate"},
            "explicit_minimum": {"result": "near_fit", "reason": "2 years experience required; applicant is entry level", "severity": "high"},
        },
        "policy_modifiers": [
            {"policy": "partner_employer_preference", "value": 5, "reason": "Acme Industrial is a SkillPointe partner"},
            {"policy": "missing_critical_requirement", "value": -8, "reason": "2-year experience requirement not met"},
        ],
        "dimension_scores": [
            ("trade_program_alignment", 25, 70, 17.50, "Welding is adjacent to fabrication but distinct specialization", False),
            ("geography_alignment", 20, 96, 19.20, "Austin TX → Austin TX — same city", False),
            ("credential_readiness", 15, 30, 4.50, "AWS cert preferred; not held. Near-fit gate triggered", False),
            ("timing_readiness", 10, 80, 8.00, "Available June 2026", False),
            ("experience_internship_alignment", 10, 20, 2.00, "Entry-level applicant vs 2-year requirement — large gap", False),
            ("industry_alignment", 5, 80, 4.00, "Manufacturing sector aligns", False),
            ("compensation_alignment", 5, 55, 2.75, "Pay $26–$34/hr higher than entry-level range", False),
            ("work_style_signal_alignment", 5, 70, 3.50, "On-site shop work — compatible", False),
            ("employer_soft_pref_alignment", 5, 50, 2.50, "No soft preferences", True),
        ],
    },
    # Match 7 — near_fit: Pipe Welder at Texas Welding Works
    {
        "job_title": "Certified Pipe Welder",
        "eligibility_status": "near_fit",
        "base_fit_score": 42.8,
        "weighted_structured_score": 50.0,
        "semantic_score": 45.0,
        "policy_adjusted_score": 38.8,
        "match_label": "moderate_fit",
        "top_strengths": [
            "Trade alignment: Welding program provides foundation for pipe welding career",
            "Geography: Same city — Austin TX",
            "Long-term career opportunity with excellent pay potential",
        ],
        "top_gaps": [
            "6G Pipe Certification required — not held",
            "3 years experience required — applicant is entry level",
            "Travel required — applicant preference not confirmed",
        ],
        "required_missing_items": [
            "6G Pipe Certification (required — critical)",
            "Minimum 3 years pipe welding experience (required)",
            "ASME Section IX qualification (preferred)",
        ],
        "recommended_next_step": "This is a future target role. Start in an entry-level welding position, gain 2–3 years experience, then pursue 6G certification. Revisit in 3+ years.",
        "confidence_level": "medium",
        "hard_gate_rationale": {
            "job_family": {"result": "pass", "reason": "Welding Technology is the foundation for pipe welding"},
            "geography": {"result": "pass", "reason": "Austin TX matches"},
            "timing_readiness": {"result": "pass", "reason": "Available June 2026"},
            "credential": {"result": "near_fit", "reason": "6G certification required — applicant does not hold it", "severity": "high"},
            "explicit_minimum": {"result": "near_fit", "reason": "3 years experience required; applicant is entry level", "severity": "high"},
        },
        "policy_modifiers": [
            {"policy": "partner_employer_preference", "value": 5, "reason": "Texas Welding Works is a SkillPointe partner"},
            {"policy": "missing_critical_requirement", "value": -12, "reason": "Required 6G certification not held"},
            {"policy": "opportunity_upside", "value": 2, "reason": "High-growth career path worth surfacing"},
        ],
        "dimension_scores": [
            ("trade_program_alignment", 25, 65, 16.25, "Welding program is the foundation but pipe welding is a specialization", False),
            ("geography_alignment", 20, 96, 19.20, "Austin TX — same city", False),
            ("credential_readiness", 15, 15, 2.25, "6G pipe cert required — not held. Critical gap", False),
            ("timing_readiness", 10, 80, 8.00, "Available June 2026", False),
            ("experience_internship_alignment", 10, 12, 1.20, "0 years vs 3 years required — significant gap", False),
            ("industry_alignment", 5, 75, 3.75, "Energy/welding sector aligns", False),
            ("compensation_alignment", 5, 40, 2.00, "Pay $32–$42/hr — well above entry level; reflects experience gap", False),
            ("work_style_signal_alignment", 5, 50, 2.50, "Moderate travel required — applicant willingness uncertain", True),
            ("employer_soft_pref_alignment", 5, 40, 2.00, "ASME Section IX preferred; not held", False),
        ],
    },
    # Match 8 — near_fit: General Construction Laborer
    {
        "job_title": "General Construction Laborer",
        "eligibility_status": "near_fit",
        "base_fit_score": 38.5,
        "weighted_structured_score": 42.0,
        "semantic_score": 40.0,
        "policy_adjusted_score": 40.5,
        "match_label": "low_fit",
        "top_strengths": [
            "Geography: San Antonio — same region, relocation feasible",
            "Low barrier to entry — no certification required",
        ],
        "top_gaps": [
            "Trade mismatch: Construction laborer is different from welding career path",
            "Pay is lower than welding roles ($16–$20/hr)",
            "Does not leverage welding training directly",
        ],
        "required_missing_items": [],
        "recommended_next_step": "This role doesn't align well with your welding training. Consider welding-specific roles first. Only pursue if you need immediate employment while seeking welding positions.",
        "confidence_level": "medium",
        "hard_gate_rationale": {
            "job_family": {"result": "near_fit", "reason": "Construction is adjacent to welding but different trade family", "severity": "moderate"},
            "geography": {"result": "pass", "reason": "San Antonio TX — same region, applicant willing to relocate"},
            "timing_readiness": {"result": "pass", "reason": "Available June 2026"},
            "credential": {"result": "pass", "reason": "No credential required"},
            "explicit_minimum": {"result": "pass", "reason": "No formal requirements"},
        },
        "policy_modifiers": [
            {"policy": "partner_employer_preference", "value": 5, "reason": "Lone Star is a partner"},
            {"policy": "missing_critical_requirement", "value": -3, "reason": "Trade family mismatch — adjacent only"},
        ],
        "dimension_scores": [
            ("trade_program_alignment", 25, 30, 7.50, "Construction laborer is a different trade family than welding", False),
            ("geography_alignment", 20, 72, 14.40, "San Antonio — same region, feasible relocation", False),
            ("credential_readiness", 15, 85, 12.75, "No credential needed", False),
            ("timing_readiness", 10, 85, 8.50, "Available June 2026", False),
            ("experience_internship_alignment", 10, 25, 2.50, "Welding experience has limited transferability to general labor", True),
            ("industry_alignment", 5, 50, 2.50, "Construction is a related but distinct industry", False),
            ("compensation_alignment", 5, 45, 2.25, "Pay $16–$20/hr is below welding entry level", False),
            ("work_style_signal_alignment", 5, 55, 2.75, "Outdoor construction work — orientation unknown", True),
            ("employer_soft_pref_alignment", 5, 40, 2.00, "Physical fitness required — not confirmed", True),
        ],
    },
    # Match 9 — ineligible: HVAC Install Tech (wrong trade, wrong credential)
    {
        "job_title": "HVAC Installation Technician",
        "eligibility_status": "ineligible",
        "base_fit_score": 18.2,
        "weighted_structured_score": 30.0,
        "semantic_score": 22.0,
        "policy_adjusted_score": 12.2,
        "match_label": "low_fit",
        "top_strengths": [
            "Geography: Austin TX — same city",
        ],
        "top_gaps": [
            "Trade mismatch: HVAC is unrelated to welding career path",
            "EPA Section 608 certification required — not held and not in pipeline",
            "HVAC certificate or apprenticeship required — applicant has welding, not HVAC",
        ],
        "required_missing_items": [
            "HVAC certificate or apprenticeship (required)",
            "EPA Section 608 certification (required)",
        ],
        "recommended_next_step": "This role requires HVAC-specific training. Not recommended unless you plan to change career paths entirely.",
        "confidence_level": "high",
        "hard_gate_rationale": {
            "job_family": {"result": "fail", "reason": "HVAC is unrelated to welding trade family"},
            "geography": {"result": "pass", "reason": "Austin TX — same city"},
            "timing_readiness": {"result": "pass", "reason": "Available June 2026"},
            "credential": {"result": "fail", "reason": "EPA 608 required — not held and not in applicant's pipeline"},
            "explicit_minimum": {"result": "fail", "reason": "HVAC certificate/apprenticeship required — applicant has welding background"},
        },
        "policy_modifiers": [
            {"policy": "missing_critical_requirement", "value": -12, "reason": "Required EPA 608 not held"},
        ],
        "dimension_scores": [
            ("trade_program_alignment", 25, 8, 2.00, "Welding has no relevance to HVAC installation", False),
            ("geography_alignment", 20, 98, 19.60, "Austin TX — same city", False),
            ("credential_readiness", 15, 5, 0.75, "EPA 608 required; not held. HVAC cert required; not held", False),
            ("timing_readiness", 10, 85, 8.50, "Timing compatible but irrelevant given trade mismatch", False),
            ("experience_internship_alignment", 10, 5, 0.50, "No HVAC experience whatsoever", False),
            ("industry_alignment", 5, 20, 1.00, "Mechanical trades are adjacent but HVAC is a distinct specialization", False),
            ("compensation_alignment", 5, 70, 3.50, "Pay range $20–$28/hr is reasonable", False),
            ("work_style_signal_alignment", 5, 55, 2.75, "On-site field work", True),
            ("employer_soft_pref_alignment", 5, 20, 1.00, "NATE cert preferred — not relevant to applicant", False),
        ],
    },
    # Match 10 — ineligible: Pipeline Welder Senior at Gulf Coast (too senior)
    {
        "job_title": "Pipeline Welder — Field",
        "eligibility_status": "ineligible",
        "base_fit_score": 22.1,
        "weighted_structured_score": 40.0,
        "semantic_score": 35.0,
        "policy_adjusted_score": 15.1,
        "match_label": "low_fit",
        "top_strengths": [
            "Trade foundation: Welding degree relevant long-term",
            "Same state — Texas",
        ],
        "top_gaps": [
            "5 years experience required — applicant has zero professional experience",
            "6G and API 1104 certifications required — not held",
            "Senior-level role; applicant is entry-level",
            "Extensive travel required",
        ],
        "required_missing_items": [
            "5 years pipeline welding experience (required — critical)",
            "6G Pipe Certification (required — critical)",
            "API 1104 qualification (required — critical)",
        ],
        "recommended_next_step": "This is a long-term career goal, not a current opportunity. Build 5+ years experience in welding roles of increasing responsibility, earn 6G and API 1104 certifications.",
        "confidence_level": "high",
        "hard_gate_rationale": {
            "job_family": {"result": "pass", "reason": "Welding program is the foundation for pipeline welding"},
            "geography": {"result": "pass", "reason": "Houston TX — same state, but requires extensive travel"},
            "timing_readiness": {"result": "pass", "reason": "Timing not the issue"},
            "credential": {"result": "fail", "reason": "6G and API 1104 required — not held"},
            "explicit_minimum": {"result": "fail", "reason": "5 years experience required; applicant has 0"},
        },
        "policy_modifiers": [
            {"policy": "partner_employer_preference", "value": 5, "reason": "Gulf Coast Energy is a partner"},
            {"policy": "missing_critical_requirement", "value": -12, "reason": "Multiple critical requirements missing"},
        ],
        "dimension_scores": [
            ("trade_program_alignment", 25, 55, 13.75, "Welding foundation relevant but pipeline welding requires extensive additional training", False),
            ("geography_alignment", 20, 45, 9.00, "Houston with frequent travel — applicant is in Austin", False),
            ("credential_readiness", 15, 5, 0.75, "6G and API 1104 required; neither held", False),
            ("timing_readiness", 10, 80, 8.00, "Timing fine but irrelevant given experience gap", False),
            ("experience_internship_alignment", 10, 5, 0.50, "0 vs 5 years — massive gap", False),
            ("industry_alignment", 5, 70, 3.50, "Energy sector — related", False),
            ("compensation_alignment", 5, 30, 1.50, "Pay $36–$50/hr reflects senior level — applicant is entry", False),
            ("work_style_signal_alignment", 5, 30, 1.50, "Frequent travel required — not suitable for new graduate", False),
            ("employer_soft_pref_alignment", 5, 30, 1.50, "Background check + drug test required", False),
        ],
    },
]


def seed_rich_data(conn) -> None:
    # ── Resolve job family IDs ──
    family_ids = {}
    for code in ("welding", "construction", "hvac"):
        conn.execute(
            "SELECT id FROM public.canonical_job_families WHERE code = %s LIMIT 1",
            (code,),
        )
        row = conn.fetchone()
        if not row:
            print(f"⚠ Job family '{code}' not found — run `supabase db reset` first")
            return
        family_ids[code] = row[0]

    # ── Get existing applicant ──
    conn.execute(
        "SELECT a.id, a.user_id FROM public.applicants a "
        "JOIN public.user_profiles up ON up.user_id = a.user_id "
        "WHERE up.role = 'applicant' LIMIT 1"
    )
    row = conn.fetchone()
    if not row:
        print("⚠ No applicant found — run seed_test_users.py first")
        return
    applicant_id, applicant_user_id = row[0], row[1]
    print(f"Found applicant: {applicant_id}")

    # ── Step 1: Enrich Jane's profile ──
    print("\n── Enriching applicant profile ──")
    conn.execute(
        """
        UPDATE public.applicants SET
            career_goals_raw = %s,
            experience_raw = %s,
            bio_raw = %s,
            willing_to_relocate = TRUE,
            willing_to_travel = FALSE,
            commute_radius_miles = 40,
            relocation_willingness_notes = %s,
            travel_willingness_notes = %s,
            timing_notes = %s
        WHERE id = %s
        """,
        (
            # career_goals_raw
            "I want to become a certified structural welder and eventually specialize in "
            "pipe welding for the energy industry. My short-term goal is to land an entry-level "
            "welding position where I can build my MIG and TIG skills under experienced welders. "
            "Within 2-3 years, I plan to earn my AWS D1.1 certification and start pursuing "
            "pipe welding opportunities. Long-term, I'd like to work on large-scale energy "
            "or infrastructure projects.",

            # experience_raw
            "Welding Technology Associate Degree Program — Austin Community College (2024–2026)\n"
            "• 200+ hours of hands-on shop time in MIG, TIG, and stick welding\n"
            "• Blueprint reading and weld symbol interpretation coursework\n"
            "• Fabricated a steel workbench from raw stock as capstone project\n"
            "• Maintained 3.6 GPA\n\n"
            "Shop Internship — Hill Country Metal Works, Austin TX (Summer 2025)\n"
            "• 200-hour internship assisting journeyman welders\n"
            "• Operated plasma cutter, angle grinder, and band saw\n"
            "• Helped prepare weld joints (beveling, cleaning, fit-up)\n"
            "• Performed basic MIG welding on non-critical assemblies under supervision\n\n"
            "Warehouse Associate — Home Depot, Austin TX (2023–2024)\n"
            "• Operated forklift (certified) and managed inventory\n"
            "• Physical labor, teamwork, and safety protocol experience",

            # bio_raw
            "I'm a hands-on learner who discovered my passion for welding during a career "
            "exploration workshop at SkillPointe. I grew up in Austin and want to build my "
            "career in the Texas skilled trades industry. I'm detail-oriented, safety-conscious, "
            "and excited to keep learning. My instructors say my TIG work is especially clean "
            "for a student at my level. Outside of welding, I enjoy fishing and working on "
            "my truck. I'm the first person in my family to pursue a trade credential and "
            "I want to prove that skilled trades are a great career path.",

            # relocation_willingness_notes
            "Willing to relocate within Texas, especially Austin metro, San Antonio, or Houston. "
            "Would prefer to stay in central Texas if possible.",

            # travel_willingness_notes
            "Prefer not to travel extensively. Light travel (day trips) is fine but I'd prefer "
            "a shop-based or local job site position.",

            # timing_notes
            "Completing my associate degree in May 2026. Available full-time starting June 1, 2026.",

            applicant_id,
        ),
    )
    print("  ✓ Applicant profile enriched with career goals, experience, and bio")

    # ── Step 2: Create / upsert employers ──
    print("\n── Creating employers ──")
    employer_ids = {}

    # Get existing Acme Industrial
    conn.execute("SELECT id FROM public.employers WHERE name = 'Acme Industrial' LIMIT 1")
    row = conn.fetchone()
    if row:
        employer_ids["Acme Industrial"] = row[0]
        print(f"  → Acme Industrial already exists: {row[0]}")

    for emp in EMPLOYERS:
        conn.execute(
            """
            INSERT INTO public.employers (name, industry, description, city, state, region, is_partner, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'seed_rich')
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (emp["name"], emp["industry"], emp["description"],
             emp["city"], emp["state"], emp["region"], emp["is_partner"]),
        )
        row = conn.fetchone()
        if row:
            employer_ids[emp["name"]] = row[0]
            print(f"  ✓ {emp['name']}: {row[0]}")
        else:
            conn.execute(
                "SELECT id FROM public.employers WHERE name = %s LIMIT 1",
                (emp["name"],),
            )
            row = conn.fetchone()
            employer_ids[emp["name"]] = row[0]
            print(f"  → {emp['name']} already exists: {row[0]}")

    # ── Step 3: Create / upsert jobs ──
    print("\n── Creating jobs ──")
    job_ids = {}  # title_raw → job id
    for job in JOBS:
        emp_id = employer_ids.get(job["employer"])
        if not emp_id:
            print(f"  ⚠ Employer '{job['employer']}' not found — skipping job '{job['title_raw']}'")
            continue
        fam_id = family_ids.get(job["family_code"])
        conn.execute(
            """
            INSERT INTO public.jobs (
                employer_id, title_raw, title_normalized,
                canonical_job_family_id,
                city, state, region,
                work_setting, travel_requirement,
                pay_min, pay_max, pay_type,
                description_raw, requirements_raw,
                experience_level, is_active, source,
                required_credentials, preferred_credentials,
                required_experience_years,
                background_check_required, drug_test_required
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, TRUE, 'seed_rich',
                %s, %s,
                %s, %s, %s
            )
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (
                emp_id, job["title_raw"], job["title_normalized"],
                fam_id,
                job["city"], job["state"], job["region"],
                job["work_setting"], job["travel_requirement"],
                job["pay_min"], job["pay_max"], job["pay_type"],
                job["description_raw"], job["requirements_raw"],
                job["experience_level"],
                job.get("required_credentials", []),
                job.get("preferred_credentials", []),
                job.get("required_experience_years"),
                job.get("background_check_required", False),
                job.get("drug_test_required", False),
            ),
        )
        row = conn.fetchone()
        if row:
            job_ids[job["title_raw"]] = row[0]
            print(f"  ✓ {job['title_raw']}: {row[0]}")
        else:
            conn.execute(
                "SELECT id FROM public.jobs WHERE title_raw = %s AND employer_id = %s LIMIT 1",
                (job["title_raw"], emp_id),
            )
            row = conn.fetchone()
            if row:
                job_ids[job["title_raw"]] = row[0]
                print(f"  → {job['title_raw']} already exists: {row[0]}")
            else:
                print(f"  ⚠ Could not find/create job '{job['title_raw']}'")

    # Also grab existing jobs from initial seed
    for title in ("Welder — Entry Level", "Metal Fabricator — Mid Level"):
        if title not in job_ids:
            conn.execute(
                "SELECT id FROM public.jobs WHERE title_raw = %s LIMIT 1",
                (title,),
            )
            row = conn.fetchone()
            if row:
                job_ids[title] = row[0]
                print(f"  → {title} (original seed): {row[0]}")

    # ── Step 4: Delete old matches for this applicant (so we get clean data) ──
    print("\n── Resetting matches ──")
    conn.execute(
        "DELETE FROM public.matches WHERE applicant_id = %s",
        (applicant_id,),
    )
    print("  ✓ Old matches deleted")

    # ── Step 5: Insert fresh matches ──
    print("\n── Creating matches ──")
    eligible_count = 0
    near_fit_count = 0
    ineligible_count = 0

    for m in MATCHES:
        jid = job_ids.get(m["job_title"])
        if not jid:
            print(f"  ⚠ Job '{m['job_title']}' not found — skipping match")
            continue

        cap = {"eligible": 1.0, "near_fit": 0.75, "ineligible": 0.35}[m["eligibility_status"]]

        conn.execute(
            """
            INSERT INTO public.matches (
                applicant_id, job_id,
                eligibility_status, hard_gate_cap,
                base_fit_score, weighted_structured_score, semantic_score,
                policy_adjusted_score, match_label,
                top_strengths, top_gaps,
                required_missing_items, recommended_next_step,
                confidence_level, requires_review,
                hard_gate_rationale, policy_modifiers,
                is_visible_to_applicant, is_visible_to_employer,
                policy_version
            ) VALUES (
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, FALSE,
                %s, %s,
                TRUE, TRUE,
                'v1'
            )
            ON CONFLICT (applicant_id, job_id) DO UPDATE SET
                eligibility_status = EXCLUDED.eligibility_status,
                hard_gate_cap = EXCLUDED.hard_gate_cap,
                base_fit_score = EXCLUDED.base_fit_score,
                weighted_structured_score = EXCLUDED.weighted_structured_score,
                semantic_score = EXCLUDED.semantic_score,
                policy_adjusted_score = EXCLUDED.policy_adjusted_score,
                match_label = EXCLUDED.match_label,
                top_strengths = EXCLUDED.top_strengths,
                top_gaps = EXCLUDED.top_gaps,
                required_missing_items = EXCLUDED.required_missing_items,
                recommended_next_step = EXCLUDED.recommended_next_step,
                confidence_level = EXCLUDED.confidence_level,
                hard_gate_rationale = EXCLUDED.hard_gate_rationale,
                policy_modifiers = EXCLUDED.policy_modifiers,
                is_visible_to_applicant = TRUE,
                is_visible_to_employer = TRUE
            RETURNING id
            """,
            (
                applicant_id, jid,
                m["eligibility_status"], cap,
                m["base_fit_score"], m["weighted_structured_score"], m["semantic_score"],
                m["policy_adjusted_score"], m["match_label"],
                json.dumps(m["top_strengths"]), json.dumps(m["top_gaps"]),
                json.dumps(m["required_missing_items"]), m["recommended_next_step"],
                m["confidence_level"],
                json.dumps(m["hard_gate_rationale"]), json.dumps(m["policy_modifiers"]),
            ),
        )
        match_row = conn.fetchone()
        match_id = match_row[0]

        # Insert dimension scores
        for (dim, weight, raw, weighted, rationale, null_applied) in m["dimension_scores"]:
            conn.execute(
                """
                INSERT INTO public.match_dimension_scores
                    (match_id, dimension, weight, raw_score, weighted_score,
                     rationale, null_handling_applied)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (match_id, dimension) DO UPDATE SET
                    raw_score = EXCLUDED.raw_score,
                    weighted_score = EXCLUDED.weighted_score,
                    rationale = EXCLUDED.rationale
                """,
                (match_id, dim, weight, raw, weighted, rationale, null_applied),
            )

        status = m["eligibility_status"]
        label = f"[{status.upper()}]"
        if status == "eligible":
            eligible_count += 1
        elif status == "near_fit":
            near_fit_count += 1
        else:
            ineligible_count += 1
        print(f"  ✓ {label:14s} {m['job_title']:<35s} score={m['policy_adjusted_score']}")

    print(f"\n── Summary ──")
    print(f"  Eligible:   {eligible_count}")
    print(f"  Near-fit:   {near_fit_count}")
    print(f"  Ineligible: {ineligible_count}")
    print(f"  Total:      {eligible_count + near_fit_count + ineligible_count}")
    print(f"\n  The applicant dashboard will show {eligible_count} eligible + {near_fit_count} near-fit matches.")
    print(f"  ({ineligible_count} ineligible matches are hidden from the applicant UI.)")


def main() -> None:
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2-binary is required. Run: pip install psycopg2-binary")
        sys.exit(1)

    print(f"Connecting to DB at {DB_URL}")
    raw_conn = psycopg2.connect(DB_URL)
    raw_conn.autocommit = False
    conn = raw_conn.cursor()

    try:
        seed_rich_data(conn)
        raw_conn.commit()
        print("\n✅ Rich test data seeded successfully!")
        print("\n  Login as applicant@test.local / Test1234! to see matches.")
        print("  Login as employer@test.local / Test1234! to see applicant rankings.")
        print(f"\n  Frontend: http://localhost:3000/login\n")
    except Exception as exc:
        raw_conn.rollback()
        print(f"\n✗ Error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()
        raw_conn.close()


if __name__ == "__main__":
    main()
