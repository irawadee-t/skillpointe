"""
llm_hooks.py — LLM integration points for the matching pipeline.

ARCHITECTURE: The matching pipeline is 100% deterministic at runtime.
LLMs are used as PRE-PROCESSING steps that run once per job or applicant
(not per match pair), then store structured signals in the database.

These hooks define WHERE LLM extraction would improve matching quality
and WHAT structured output it should produce. Each hook has:
  - A description of what the LLM would extract
  - The expected output schema
  - A fallback heuristic (what the system does today without LLM)
  - An estimate of impact on matching quality

Integration pattern:
  1. Job is scraped/created → trigger LLM extraction → store in extracted_job_signals
  2. Applicant completes profile → trigger LLM extraction → store in extracted_applicant_signals
  3. Matching engine reads pre-extracted signals from DB → uses in gates/scoring
  4. Cost: O(jobs + applicants) LLM calls, NOT O(jobs × applicants)

The extracted_*_signals tables already exist in the schema.
Run `scripts/run_extraction.py` to populate them.
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Hook 1: Job Description Skill Extraction
# ---------------------------------------------------------------------------
# Current fallback: regex keyword matching against SKILL_TAXONOMY (text_scorer.py)
# LLM improvement: Understand nuanced skill requirements that keywords miss
#   e.g., "comfortable working at heights" → physical_fitness, climbing
#   e.g., "experience with Allen-Bradley PLCs" → plc_programming, industrial_controls
# Impact: HIGH — directly improves skills overlap scoring (30% of semantic score)
# Cost: ~1 LLM call per job, store result in extracted_job_signals.required_skills

JOB_SKILL_EXTRACTION_SCHEMA = {
    "required_skills": [
        {"skill": "str — canonical skill name",
         "importance": "critical | important | preferred",
         "context": "str — original text snippet"}
    ],
    "preferred_skills": [
        {"skill": "str", "importance": "preferred", "context": "str"}
    ],
}


# ---------------------------------------------------------------------------
# Hook 2: Experience Level Classification
# ---------------------------------------------------------------------------
# Current fallback: title keyword matching ("senior", "journey", "lead", etc.)
# LLM improvement: Understand context-specific seniority
#   e.g., "Technician I" → entry, "Technician III" → mid
#   e.g., "Journey Level Electrician" → mid (requires 4+ years field time)
#   e.g., "Technical Trainer" → mid (requires teaching experience, not entry)
# Impact: HIGH — directly affects seniority gate (pass/fail)
# Cost: ~1 LLM call per job, store in jobs.experience_level

EXPERIENCE_CLASSIFICATION_SCHEMA = {
    "experience_level": "entry | mid | senior",
    "min_years_required": "int | null",
    "reasoning": "str — why this classification",
}


# ---------------------------------------------------------------------------
# Hook 3: Education Requirement Parsing
# ---------------------------------------------------------------------------
# Current fallback: regex matching for degree types + "or equivalent"
# LLM improvement: Handle complex phrasing like:
#   "Associate's degree, trade/vocational certification, Military training
#    or similar experience in electrical-related disciplines"
#   → level=associates, or_equivalent=True, accepted_alternatives=[trade_cert, military]
# Impact: MEDIUM — improves credential gate accuracy
# Cost: ~1 LLM call per job

EDUCATION_REQUIREMENT_SCHEMA = {
    "min_education": "high_school | trade_cert | associates | bachelors | none",
    "or_equivalent": "bool",
    "accepted_alternatives": ["trade_cert", "military", "experience"],
    "field_preference": "str | null",
}


# ---------------------------------------------------------------------------
# Hook 4: Soft Preference Extraction
# ---------------------------------------------------------------------------
# Current fallback: keyword matching for 12 soft skill categories
# LLM improvement: Extract nuanced employer preferences from free text
#   e.g., "must be a self-starter who thrives in ambiguous environments"
#   → self-motivated, adaptability, independence
# Impact: MEDIUM — improves employer_soft_pref_alignment (5% of score)
# Cost: ~1 LLM call per job

SOFT_PREFERENCE_SCHEMA = {
    "work_style_signals": [
        {"signal": "str — e.g., 'teamwork', 'self-motivated'",
         "strength": "required | preferred",
         "context": "str"}
    ],
}


# ---------------------------------------------------------------------------
# Hook 5: Applicant Profile Enrichment
# ---------------------------------------------------------------------------
# Current fallback: infer skills from trade family, parse text fields
# LLM improvement: Extract structured skills/experience from essays, bio
#   e.g., essay: "I interned at a solar panel installation company where
#   I learned about grid-tie inverters and NEC Article 690"
#   → skills: [solar_installation, grid_tie_inverters, nec_code]
#   → experience: {type: "internship", relevance: "high", domain: "solar_energy"}
# Impact: HIGH for applicants with rich text data, LOW for sparse profiles
# Cost: ~1 LLM call per applicant

APPLICANT_ENRICHMENT_SCHEMA = {
    "skills_extracted": [
        {"skill": "str", "source_field": "str", "confidence": "float 0-1"}
    ],
    "certifications_extracted": [
        {"name": "str", "status": "active | pending | expired"}
    ],
    "experience_signals": [
        {"description": "str", "relevance": "high | medium | low",
         "duration_months": "int | null"}
    ],
    "work_style_signals": [
        {"signal": "str", "evidence": "str"}
    ],
}


# ---------------------------------------------------------------------------
# Hook 6: Match Explanation Generation (on-demand)
# ---------------------------------------------------------------------------
# Current fallback: template-based explanations from gate/dimension results
# LLM improvement: Generate natural, personalized explanations
#   e.g., "Your Electrician training at San Jose Trade School aligns well
#   with this role's need for NEC code knowledge and circuit troubleshooting.
#   The main gap is 2 years of field experience — your program training
#   covers the fundamentals, but the employer prefers hands-on experience."
# Impact: HIGH for user experience, ZERO for match quality
# Cost: ~1 LLM call per match VIEW (lazy, only when user clicks)
# This is the ONLY hook that runs per-match, but only on user action

EXPLANATION_SCHEMA = {
    "summary": "str — 2-3 sentence personalized explanation",
    "strengths_detail": ["str — expanded strength explanation"],
    "gaps_detail": ["str — expanded gap explanation with actionable advice"],
    "next_steps": ["str — concrete actions the applicant can take"],
}


# ---------------------------------------------------------------------------
# Integration Priority (recommended build order)
# ---------------------------------------------------------------------------
# 1. Hook 2 (Experience Level) — highest ROI, prevents wrong seniority matches
# 2. Hook 1 (Job Skills) — biggest scoring impact
# 3. Hook 3 (Education) — fixes "or equivalent" edge cases
# 4. Hook 5 (Applicant Enrichment) — valuable when profiles have text
# 5. Hook 4 (Soft Preferences) — nice-to-have, small weight
# 6. Hook 6 (Explanations) — UX polish, no matching impact


def get_llm_integration_status() -> dict[str, Any]:
    """Report which LLM hooks are active vs using fallbacks."""
    return {
        "job_skill_extraction": "fallback — regex keyword matching",
        "experience_classification": "fallback — title keyword matching",
        "education_parsing": "fallback — regex with or_equivalent detection",
        "soft_preference_extraction": "fallback — 12-category keyword matching",
        "applicant_enrichment": "fallback — family-based skill inference",
        "explanation_generation": "fallback — template-based from gates/dimensions",
        "note": "Run scripts/run_extraction.py with OPENAI_API_KEY to enable LLM hooks",
    }
