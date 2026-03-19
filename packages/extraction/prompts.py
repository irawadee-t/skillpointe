"""
prompts.py — Prompt templates for the extraction pipeline.

All prompts use {}-style placeholders filled by the calling extractor.
Double braces {{ }} are literal braces in the JSON schema examples.
"""

PROMPT_VERSION = "v1.0"

# -----------------------------------------------------------------------
# Canonical family codes (shared reference for both prompts)
# -----------------------------------------------------------------------
_FAMILY_CODES = (
    "electrical, plumbing, hvac, construction, welding, automotive, "
    "manufacturing, logistics, aviation, wind_energy, energy_lineman, "
    "solar_energy, robotics, heavy_equipment, healthcare_support, "
    "it_support, culinary, childcare_education, cosmetology, security, "
    "administrative"
)


# -----------------------------------------------------------------------
# Applicant extraction
# -----------------------------------------------------------------------

APPLICANT_SYSTEM = (
    "You are a structured data extraction system for SkillPointe Match, "
    "a skilled-trades workforce matching platform.\n\n"
    "Extract structured signals from applicant profile text. "
    "Return ONLY valid JSON matching the schema the user provides.\n\n"
    "Confidence levels:\n"
    "- high: explicit, unambiguous evidence in the text\n"
    "- medium: reasonable inference from context\n"
    "- low: weak signal or significant interpretation required\n\n"
    "Rules:\n"
    "- Only extract what is evidenced in the text\n"
    "- Never hallucinate skills or certifications\n"
    "- If a section is empty, return an empty array for that field\n"
    "- Include evidence_snippet (the exact phrase from source) for skills and certs"
)

APPLICANT_USER = """Extract structured signals from this applicant profile.

**Program**: {program_name}
**Personal Statement / Bio**: {bio}
**Experience / Internship**: {experience}
**Career Goals**: {career_goals}
**Background Essay**: {essay_background}
**Activities / Extracurriculars**: {activities}

Return JSON with this exact structure:
{{
  "skills": [
    {{"skill": "string", "confidence": "high|medium|low", "evidence_snippet": "quote from text"}}
  ],
  "certifications": [
    {{"name": "string", "status": "obtained|in_progress|planned", "confidence": "high|medium|low", "evidence_snippet": "quote from text"}}
  ],
  "desired_job_families": [
    {{"family_code": "one of: {family_codes}", "confidence": "high|medium|low"}}
  ],
  "work_style_signals": [
    {{"signal": "string", "value": "string or boolean", "confidence": "high|medium|low"}}
  ],
  "experience_signals": [
    {{"description": "string", "years_estimated": null, "relevance": "high|medium|low", "confidence": "high|medium|low"}}
  ],
  "readiness_signals": [
    {{"type": "completion|availability|enrollment", "value": "string", "confidence": "high|medium|low"}}
  ],
  "intent_signals": [
    {{"type": "career_goal|preference|constraint", "description": "string", "confidence": "high|medium|low"}}
  ],
  "overall_confidence": "high|medium|low"
}}"""


# -----------------------------------------------------------------------
# Job extraction
# -----------------------------------------------------------------------

JOB_SYSTEM = (
    "You are a structured data extraction system for SkillPointe Match, "
    "a skilled-trades workforce matching platform.\n\n"
    "Extract structured signals from job posting text. "
    "Return ONLY valid JSON matching the schema the user provides.\n\n"
    "Confidence levels:\n"
    "- high: explicit, unambiguous evidence in the text\n"
    "- medium: reasonable inference from context\n"
    "- low: weak signal or significant interpretation required\n\n"
    "Rules:\n"
    "- Distinguish clearly between required and preferred items\n"
    "- Never hallucinate requirements not in the text\n"
    "- If a section is empty, return an empty array for that field"
)

JOB_USER = """Extract structured signals from this job posting.

**Title**: {title}
**Description**: {description}
**Requirements**: {requirements}
**Preferred Qualifications**: {preferred_qualifications}

Return JSON with this exact structure:
{{
  "required_skills": [
    {{"skill": "string", "importance": "critical|important|nice_to_have", "confidence": "high|medium|low", "evidence_snippet": "quote from text"}}
  ],
  "preferred_skills": [
    {{"skill": "string", "confidence": "high|medium|low", "evidence_snippet": "quote from text"}}
  ],
  "required_credentials": [
    {{"credential": "string", "confidence": "high|medium|low"}}
  ],
  "preferred_credentials": [
    {{"credential": "string", "confidence": "high|medium|low"}}
  ],
  "job_family_signals": [
    {{"family_code": "one of: {family_codes}", "confidence": "high|medium|low"}}
  ],
  "experience_level": {{
    "minimum_years": null,
    "preferred_years": null,
    "level": "entry|mid|senior|any",
    "confidence": "high|medium|low"
  }},
  "physical_requirements": [
    {{"requirement": "string", "confidence": "high|medium|low"}}
  ],
  "work_style_signals": [
    {{"signal": "string", "value": "string or boolean", "confidence": "high|medium|low"}}
  ],
  "overall_confidence": "high|medium|low"
}}"""


# -----------------------------------------------------------------------
# Verifier
# -----------------------------------------------------------------------

VERIFIER_SYSTEM = (
    "You are a verification system for SkillPointe Match extraction outputs. "
    "Check that extractions are consistent with source text and flag issues.\n"
    "Return ONLY valid JSON."
)

VERIFIER_USER = """Review this extraction output against the original source text.

**Entity Type**: {entity_type}

**Source Text**:
{source_text}

**Extraction Output**:
{extraction_json}

Return JSON:
{{
  "is_consistent": true_or_false,
  "confidence_appropriate": true_or_false,
  "issues": [
    {{"type": "hallucination|missing_signal|wrong_confidence|taxonomy_mismatch|ambiguity", "description": "string", "severity": "critical|warning|info"}}
  ],
  "suggested_confidence": "high|medium|low",
  "needs_human_review": true_or_false,
  "review_reason": "string or null"
}}"""


def format_applicant_prompt(
    program_name: str, bio: str, experience: str, career_goals: str,
    essay_background: str = "", activities: str = "",
) -> str:
    return APPLICANT_USER.format(
        program_name=program_name or "(not provided)",
        bio=bio or "(not provided)",
        experience=experience or "(not provided)",
        career_goals=career_goals or "(not provided)",
        essay_background=essay_background or "(not provided)",
        activities=activities or "(not provided)",
        family_codes=_FAMILY_CODES,
    )


def format_job_prompt(
    title: str, description: str, requirements: str, preferred_qualifications: str,
) -> str:
    return JOB_USER.format(
        title=title or "(not provided)",
        description=description or "(not provided)",
        requirements=requirements or "(not provided)",
        preferred_qualifications=preferred_qualifications or "(not provided)",
        family_codes=_FAMILY_CODES,
    )


def format_verifier_prompt(
    entity_type: str, source_text: str, extraction_json: str,
) -> str:
    return VERIFIER_USER.format(
        entity_type=entity_type,
        source_text=source_text[:4000],
        extraction_json=extraction_json[:4000],
    )
