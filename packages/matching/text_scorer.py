"""
text_scorer.py — Intelligent text-based semantic scoring for applicant-job matching.

Extracts structured signals from free text using NLP heuristics, then computes
a nuanced semantic alignment score (0–100). Designed to work well WITHOUT LLM
calls by doing deep text analysis.

Architecture:
  1. Parse job descriptions into structured requirements
     (years of experience, credentials, skills, physical, education)
  2. Extract applicant capabilities from profile text
  3. Score match quality across multiple dimensions
  4. Return composite score + detailed rationale

When LLM-based extraction is available (extracted_*_signals tables),
the engine prefers those signals. This module is the fallback.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Trades skill taxonomy — organized by family
# ---------------------------------------------------------------------------
SKILL_TAXONOMY: dict[str, list[tuple[str, list[str]]]] = {
    "electrical": [
        ("electrical wiring", ["wiring", "wire", "electrical wiring", "conduit", "raceway"]),
        ("circuit troubleshooting", ["troubleshoot", "troubleshooting", "diagnose", "fault finding"]),
        ("nec code", ["nec", "national electrical code", "code compliance"]),
        ("plc programming", ["plc", "programmable logic", "ladder logic", "allen-bradley", "siemens"]),
        ("motor controls", ["motor control", "vfd", "variable frequency", "starter"]),
        ("high voltage", ["high voltage", "medium voltage", "480v", "4160v"]),
        ("low voltage", ["low voltage", "24v", "12v", "signal wiring"]),
        ("transformer", ["transformer", "switchgear", "breaker", "panel"]),
        ("electrical safety", ["lockout", "tagout", "loto", "arc flash", "nfpa 70e"]),
        ("blueprint reading", ["blueprint", "schematic", "electrical drawing", "single line"]),
        ("power distribution", ["power distribution", "distribution", "ups", "uninterruptible"]),
        ("ac/dc power", ["ac power", "dc power", "ac and dc", "ac/dc"]),
        ("industrial electrical", ["industrial", "commercial", "plant electrical"]),
    ],
    "welding": [
        ("mig welding", ["mig", "gmaw", "gas metal arc"]),
        ("tig welding", ["tig", "gtaw", "gas tungsten arc"]),
        ("stick welding", ["stick", "smaw", "shielded metal arc"]),
        ("flux core", ["flux core", "fcaw"]),
        ("pipe welding", ["pipe weld", "pipe fitting"]),
        ("structural welding", ["structural", "structural steel", "fabrication"]),
        ("aws certification", ["aws", "aws d1", "certified welder"]),
        ("blueprint reading", ["blueprint", "weld symbol", "drawing"]),
        ("metal fabrication", ["fabricat", "cutting", "grinding", "fitting"]),
        ("inspection", ["weld inspection", "visual inspection", "quality"]),
    ],
    "hvac": [
        ("refrigeration", ["refriger", "r-410a", "r-22", "chiller"]),
        ("hvac systems", ["hvac", "heating", "ventilation", "air conditioning"]),
        ("ductwork", ["ductwork", "sheet metal", "duct"]),
        ("epa certification", ["epa 608", "epa certification", "refrigerant"]),
        ("controls", ["thermostat", "ddc", "building automation", "bas", "bms"]),
        ("electrical", ["electrical", "wiring", "circuit"]),
        ("troubleshooting", ["troubleshoot", "diagnose", "repair"]),
        ("preventive maintenance", ["preventive", "pm", "scheduled maintenance"]),
        ("commissioning", ["commissioning", "startup", "start-up"]),
        ("piping", ["piping", "brazing", "soldering", "copper"]),
    ],
    "manufacturing": [
        ("cnc operation", ["cnc", "computer numerical", "machining center"]),
        ("quality control", ["quality control", "qc", "quality assurance", "qa", "inspection"]),
        ("lean manufacturing", ["lean", "six sigma", "kaizen", "5s", "continuous improvement"]),
        ("machine operation", ["machine operator", "press", "lathe", "mill", "grind"]),
        ("assembly", ["assembly", "assemble", "build", "production line"]),
        ("safety", ["safety", "osha", "ppe", "lockout", "hazmat"]),
        ("forklift", ["forklift", "material handling", "warehouse"]),
        ("blueprint reading", ["blueprint", "drawing", "specification"]),
        ("maintenance", ["maintenance", "repair", "troubleshoot", "preventive"]),
        ("production", ["production", "manufacturing", "output", "throughput"]),
        ("robotics", ["robot", "automated", "automation", "plc"]),
        ("process improvement", ["process improvement", "standard work", "spc"]),
    ],
    "automotive": [
        ("engine repair", ["engine", "powertrain", "motor"]),
        ("brake systems", ["brake", "abs", "braking"]),
        ("electrical systems", ["electrical", "wiring", "diagnostic"]),
        ("diagnostic tools", ["diagnostic", "obd", "scan tool", "multimeter"]),
        ("transmission", ["transmission", "drivetrain", "gear"]),
        ("ase certification", ["ase", "certified", "master technician"]),
        ("suspension", ["suspension", "steering", "alignment"]),
        ("a/c systems", ["a/c", "air conditioning", "climate control"]),
        ("diesel", ["diesel", "heavy duty", "commercial vehicle"]),
        ("preventive maintenance", ["preventive", "scheduled service", "pm"]),
    ],
    "construction": [
        ("framing", ["framing", "framer", "rough carpentry"]),
        ("concrete", ["concrete", "foundation", "formwork"]),
        ("roofing", ["roofing", "roof", "shingle"]),
        ("drywall", ["drywall", "sheetrock", "taping"]),
        ("safety", ["osha", "fall protection", "scaffold"]),
        ("power tools", ["power tool", "saw", "drill", "nail gun"]),
        ("blueprint reading", ["blueprint", "drawing", "plan reading"]),
        ("rigging", ["rigging", "crane", "lifting"]),
        ("earthwork", ["excavat", "grading", "earthwork"]),
        ("site management", ["site", "project", "schedule"]),
    ],
    "logistics": [
        ("warehouse operations", ["warehouse", "distribution", "fulfillment"]),
        ("forklift operation", ["forklift", "pallet jack", "order picker"]),
        ("inventory management", ["inventory", "cycle count", "stock"]),
        ("shipping receiving", ["shipping", "receiving", "dock"]),
        ("material handling", ["material handling", "loading", "unloading"]),
        ("safety", ["safety", "osha", "ppe"]),
        ("rf scanner", ["rf scanner", "wms", "barcode"]),
        ("packaging", ["packaging", "packing", "labeling"]),
    ],
    "aviation": [
        ("aircraft maintenance", ["aircraft", "airframe", "powerplant"]),
        ("faa regulations", ["faa", "far", "airworthiness"]),
        ("a&p license", ["a&p", "airframe and powerplant"]),
        ("inspection", ["inspection", "non-destructive", "ndt", "ndi"]),
        ("avionics", ["avionics", "electronics", "navigation"]),
        ("sheet metal", ["sheet metal", "rivet", "structural repair"]),
        ("hydraulics", ["hydraulic", "pneumatic"]),
        ("turbine engines", ["turbine", "jet engine", "gas turbine"]),
        ("safety", ["safety", "hazmat", "foi"]),
        ("documentation", ["logbook", "maintenance record", "documentation"]),
    ],
    "wind_energy": [
        ("wind turbine", ["wind turbine", "wind tech", "turbine maintenance"]),
        ("high voltage", ["high voltage", "medium voltage", "electrical"]),
        ("hydraulics", ["hydraulic", "pneumatic"]),
        ("safety", ["climbing", "harness", "fall protection", "rescue"]),
        ("troubleshooting", ["troubleshoot", "diagnose", "fault"]),
        ("gearbox", ["gearbox", "generator", "mechanical"]),
    ],
    "energy_lineman": [
        ("line work", ["lineman", "line worker", "overhead line"]),
        ("high voltage", ["high voltage", "transmission", "distribution"]),
        ("climbing", ["climbing", "pole", "tower"]),
        ("safety", ["arc flash", "grounding", "live line"]),
        ("cdl driving", ["cdl", "commercial driver", "bucket truck"]),
    ],
    "_general": [
        ("safety awareness", ["safety", "osha", "ppe", "hazard", "incident"]),
        ("teamwork", ["team", "collaborate", "cross-functional"]),
        ("communication", ["communication", "written", "verbal", "report"]),
        ("problem solving", ["problem solving", "troubleshoot", "root cause", "analytical"]),
        ("reliability", ["reliable", "punctual", "attendance", "dependable"]),
        ("physical fitness", ["physical", "lift", "stand", "manual labor"]),
        ("computer literacy", ["computer", "microsoft", "excel", "email"]),
        ("driver license", ["driver", "license", "cdl", "valid driver"]),
        ("hand tools", ["hand tool", "wrench", "screwdriver", "plier"]),
        ("blueprint reading", ["blueprint", "schematic", "drawing", "diagram"]),
    ],
}


# ---------------------------------------------------------------------------
# Stop words for text comparison (extended)
# ---------------------------------------------------------------------------
_STOP_WORDS = frozenset({
    "this", "that", "with", "from", "have", "been", "will", "were",
    "they", "them", "their", "your", "about", "which", "when",
    "would", "could", "should", "than", "then", "into", "also",
    "more", "some", "such", "only", "other", "very", "just",
    "like", "make", "made", "work", "must", "what", "does",
    "each", "every", "these", "those", "being", "doing",
    "know", "most", "need", "come", "here", "there", "over",
    "many", "much", "well", "back", "even", "help", "take",
    "through", "good", "great", "first", "after", "year", "years",
    "able", "want", "look", "part", "long", "high", "same",
    "right", "still", "find", "both", "between", "under",
    "company", "electric", "schneider", "including",
})


# ---------------------------------------------------------------------------
# Job description requirement parser
# ---------------------------------------------------------------------------

def _parse_experience_years(text: str) -> int | None:
    """Extract minimum years of experience from job description text."""
    patterns = [
        r'(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:related\s+)?(?:field\s+)?(?:service\s+)?(?:experience|work)',
        r'minimum\s+(?:of\s+)?(\d+)\s*(?:years?|yrs?)',
        r'(\d+)\+?\s*(?:years?|yrs?)\s+(?:in|of)\s+',
        r'at\s+least\s+(\d+)\s*(?:years?|yrs?)',
    ]
    min_years = None
    for pat in patterns:
        for m in re.finditer(pat, text.lower()):
            y = int(m.group(1))
            if 0 < y <= 30:
                if min_years is None or y < min_years:
                    min_years = y
    return min_years


def _parse_education_level(text: str) -> str | None:
    """Extract minimum education level from job description."""
    text_lower = text.lower()
    if re.search(r"bachelor'?s?\s+degree|four.year\s+degree|4.year\s+degree|bs\s+in\s+|ba\s+in\s+", text_lower):
        return "bachelors"
    if re.search(r"associate'?s?\s+degree|two.year\s+degree|2.year\s+degree|aas\s+|as\s+degree", text_lower):
        return "associates"
    if re.search(r"trade.*?(?:school|certif)|vocational|technical\s+(?:school|certif|diploma|training)", text_lower):
        return "trade_cert"
    if re.search(r"high\s+school|ged|diploma", text_lower):
        return "high_school"
    if re.search(r"military\s+train", text_lower):
        return "military"
    return None


def _parse_certifications_required(text: str) -> list[str]:
    """Extract certification/license requirements from job description."""
    found: list[str] = []
    text_lower = text.lower()
    cert_patterns = [
        (r"(?:epa|epa[\s-]*608)\s*certif", "EPA 608"),
        (r"nfpa[\s-]*70e", "NFPA 70E"),
        (r"osha\s+(?:10|30)", "OSHA certification"),
        (r"a&p\s+(?:license|certif|mechanic)", "A&P license"),
        (r"\base\b[\s-]*certif", "ASE certification"),
        (r"\baws\b\s+(?:d1|certif)", "AWS welding certification"),
        (r"\bcdl\b|commercial\s+driver.?s?\s+licens", "CDL"),
        (r"journeyman", "Journeyman license"),
        (r"master\s+electric", "Master Electrician license"),
        (r"first\s+aid|cpr", "First Aid/CPR"),
        (r"forklift\s+(?:certif|licens|operat)", "Forklift certification"),
        (r"valid\s+(?:driver|driving).?s?\s+licens", "Valid driver's license"),
        (r"(?:state|local)\s+(?:electric|plumb|hvac|mechan)\w*\s+licens", "State trade license"),
        (r"hvac\s+certif|(?:epa|universal)\s+refrigerant", "HVAC certification"),
        (r"weld(?:ing)?\s+certif", "Welding certification"),
        (r"electric(?:ian|al)\s+licens", "Electrician license"),
        (r"\bpmp\b", "PMP certification"),
        (r"comptia", "CompTIA certification"),
        (r"six\s+sigma|lean\s+(?:certif|green\s+belt|black\s+belt)", "Lean/Six Sigma"),
        (r"\bnccer\b", "NCCER certification"),
    ]
    for pat, label in cert_patterns:
        if re.search(pat, text_lower):
            found.append(label)
    return found


def _parse_education_required(text: str) -> dict[str, Any] | None:
    """
    Extract structured education requirement from job description.
    Returns dict with 'level', 'field_preference', 'or_equivalent' keys,
    or None if no education requirement detected.
    """
    text_lower = text.lower()

    or_equiv = bool(re.search(r"or\s+equivalent|equivalent\s+(?:experience|combination)", text_lower))

    if re.search(r"bachelor'?s?\s+degree|four[\s-]year\s+degree|4[\s-]year\s+degree|\bbs\b\s+in\s+|\bba\b\s+in\s+", text_lower):
        return {"level": "bachelors", "or_equivalent": or_equiv}
    if re.search(r"associate'?s?\s+degree|two[\s-]year\s+degree|2[\s-]year\s+degree|\baas\b|\bas\s+degree", text_lower):
        return {"level": "associates", "or_equivalent": or_equiv}
    if re.search(r"trade\s*(?:school|certif)|vocational|technical\s+(?:school|certif|diploma|training)|apprenticeship", text_lower):
        return {"level": "trade_cert", "or_equivalent": or_equiv}
    if re.search(r"high\s+school\s+(?:diploma|degree|education)|ged\b|diploma\s+(?:or|required)", text_lower):
        return {"level": "high_school", "or_equivalent": or_equiv}
    if re.search(r"military\s+train", text_lower):
        return {"level": "military", "or_equivalent": or_equiv}

    return None


def _parse_physical_requirements(text: str) -> list[str]:
    """Extract physical requirements from job description."""
    found = []
    text_lower = text.lower()
    if re.search(r"lift.*?(\d+)\s*(?:pounds|lbs)", text_lower):
        m = re.search(r"lift.*?(\d+)\s*(?:pounds|lbs)", text_lower)
        found.append(f"lift {m.group(1)} lbs")
    if re.search(r"stand.*?extended|standing.*?long|on\s+(?:your|their)\s+feet", text_lower):
        found.append("extended standing")
    if re.search(r"climb|height|ladder|aerial", text_lower):
        found.append("climbing/heights")
    if re.search(r"confined\s+space", text_lower):
        found.append("confined spaces")
    if re.search(r"outdoor|outside|weather|heat|cold", text_lower):
        found.append("outdoor work")
    if re.search(r"travel.*?(?:require|frequent|overnight|region|country)", text_lower):
        found.append("travel required")
    return found


# ---------------------------------------------------------------------------
# Applicant profile parser
# ---------------------------------------------------------------------------

def _estimate_applicant_experience_years(applicant: dict[str, Any]) -> int | None:
    """Estimate years of professional experience from applicant profile.
    
    Uses explicit data first, then text parsing, then enrollment status inference.
    Returns 0 for students/recent grads when no explicit experience is found.
    """
    # 1. Explicit years_experience field
    explicit = applicant.get("years_experience")
    if explicit is not None:
        return int(explicit)

    # 2. Parse from text fields
    text_parts = []
    for f in ("experience_raw", "internship_details", "bio_raw", "essay_background"):
        v = applicant.get(f)
        if v:
            text_parts.append(v)
    text = " ".join(text_parts).lower()

    if text:
        for pat in [r'(\d+)\+?\s*years?\s+(?:of\s+)?experience', r'worked\s+(?:for\s+)?(\d+)\s*years?']:
            m = re.search(pat, text)
            if m:
                return int(m.group(1))

    # 3. Infer from enrollment/completion status
    enrollment = applicant.get("enrollment_status", "")
    if enrollment in ("enrolled", "in_progress", "vocational_certificate"):
        return 0

    from datetime import date
    completion = applicant.get("expected_completion_date") or applicant.get("completion_date")
    if completion:
        if isinstance(completion, str):
            try:
                completion = date.fromisoformat(completion)
            except ValueError:
                completion = None
        if completion and completion >= date.today():
            return 0  # not yet graduated
        if completion and (date.today() - completion).days < 365:
            return 0  # graduated within last year

    # 4. Internship = ~1 year equivalent
    internship = applicant.get("has_internship") or applicant.get("internship_completed")
    if internship:
        return 1

    degree = applicant.get("degree_type", "")
    if degree in ("skilled_trades_certificate", "vocational_certificate", "associates"):
        return 0  # trade school student/recent grad

    return None


def _estimate_applicant_education(applicant: dict[str, Any]) -> str | None:
    """
    Estimate education level from structured applicant data first,
    then fall back to text parsing.

    Priority:
      1. degree_type (structured enum from DB)
      2. enrollment_status (structured enum from DB)
      3. program_name_raw text analysis
      4. Text fields (bio, experience)
    """
    # 1. Structured degree_type (most reliable)
    degree_type = applicant.get("degree_type")
    if degree_type:
        degree_map = {
            "associates": "associates",
            "bachelors": "bachelors",
            "skilled_trades_certificate": "trade_cert",
            "apprenticeship": "trade_cert",
            "dual_enrollment": "high_school",
            "other": "trade_cert",
        }
        mapped = degree_map.get(degree_type)
        if mapped:
            return mapped

    # 2. Enrollment status
    enrollment = applicant.get("enrollment_status")
    if enrollment:
        enrollment_map = {
            "community_college": "associates",
            "bachelors_plus": "bachelors",
            "vocational_certificate": "trade_cert",
            "apprenticeship": "trade_cert",
            "dual_enrollment": "high_school",
            "high_school": "high_school",
        }
        mapped = enrollment_map.get(enrollment)
        if mapped:
            return mapped

    # 3. Program name text analysis
    prog = (applicant.get("program_name_raw") or "").lower()
    if prog:
        if re.search(r"bachelor|b\.s\.|b\.a\.", prog):
            return "bachelors"
        if re.search(r"associate|a\.s\.|a\.a\.|aas", prog):
            return "associates"
        if re.search(r"apprentice", prog):
            return "trade_cert"
        if re.search(r"certificate|vocational|technical", prog):
            return "trade_cert"
        # Default: if they're in a named program, assume at least trade_cert level
        return "trade_cert"

    # 4. Text field fallback
    bio = (applicant.get("bio_raw") or "").lower()
    exp = (applicant.get("experience_raw") or "").lower()
    text = f"{bio} {exp}"

    if re.search(r"bachelor|b\.s\.|b\.a\.", text):
        return "bachelors"
    if re.search(r"associate|a\.s\.|a\.a\.|community college", text):
        return "associates"
    if re.search(r"trade\s+school|vocational|technical\s+school|certificate\s+program|apprentice", text):
        return "trade_cert"
    if re.search(r"high\s+school|ged", text):
        return "high_school"
    if re.search(r"military", text):
        return "military"

    return None


# ---------------------------------------------------------------------------
# Core skill extraction
# ---------------------------------------------------------------------------

def extract_skills_from_text(text: str, family_hint: str | None = None) -> set[str]:
    """Extract canonical skill tokens from free text."""
    if not text:
        return set()

    text_lower = text.lower()
    found: set[str] = set()

    families_to_check = []
    if family_hint and family_hint in SKILL_TAXONOMY:
        families_to_check.append(family_hint)
    from .normalizer import JOB_FAMILY_ADJACENCY
    if family_hint:
        for adj in JOB_FAMILY_ADJACENCY.get(family_hint, set()):
            if adj in SKILL_TAXONOMY and adj not in families_to_check:
                families_to_check.append(adj)
    for fam in SKILL_TAXONOMY:
        if fam not in families_to_check:
            families_to_check.append(fam)

    for fam in families_to_check:
        for canonical_skill, keywords in SKILL_TAXONOMY[fam]:
            if canonical_skill in found:
                continue
            for kw in keywords:
                if kw in text_lower:
                    found.add(canonical_skill)
                    break

    return found


def extract_job_skills(job: dict[str, Any]) -> set[str]:
    """Extract skill signals from all available job text fields."""
    parts = []
    for field in ("description_raw", "requirements_raw", "preferred_qualifications_raw", "title_raw"):
        val = job.get(field)
        if val:
            parts.append(val)
    text = " ".join(parts)
    family = job.get("canonical_job_family_code")
    return extract_skills_from_text(text, family)


def extract_applicant_skills(applicant: dict[str, Any]) -> set[str]:
    """Extract skill signals from all available applicant text fields.
    
    When explicit text data is sparse (common for trade school students),
    infer baseline skills from the applicant's trade family. A student
    completing an Electrician program is implicitly trained in wiring,
    troubleshooting, code compliance, etc.
    """
    parts = []
    for field in ("experience_raw", "internship_details", "essay_background",
                  "essay_impact", "bio_raw", "career_goals_raw", "program_name_raw"):
        val = applicant.get(field)
        if val:
            parts.append(val)
    text = " ".join(parts)
    family = applicant.get("canonical_job_family_code")
    explicit_skills = extract_skills_from_text(text, family)

    # If sparse profile, infer baseline skills from trade family
    # A student in an accredited program is training in the core skills of their trade
    if len(explicit_skills) < 3 and family and family in SKILL_TAXONOMY:
        family_skills = SKILL_TAXONOMY[family]
        # Add the core skills (first 6) from their trade family as implicit skills
        for canonical_skill, _keywords in family_skills[:6]:
            explicit_skills.add(canonical_skill)
        # Also add general skills that all trade programs teach
        for canonical_skill, _keywords in SKILL_TAXONOMY.get("_general", [])[:4]:
            explicit_skills.add(canonical_skill)

    return explicit_skills


# ---------------------------------------------------------------------------
# Smart text comparison using weighted keyword matching
# ---------------------------------------------------------------------------

def _extract_meaningful_words(text: str) -> dict[str, float]:
    """
    Extract words with importance weights using a simple TF heuristic.
    Words appearing in "requirements" sections get higher weight.
    """
    if not text:
        return {}

    text_lower = text.lower()
    words: dict[str, float] = {}

    in_requirements = False
    for line in text_lower.split("\n"):
        line = line.strip()
        if not line:
            continue

        if re.search(r'(?:require|qualif|must\s+have|minimum|essential)', line):
            in_requirements = True
        elif re.search(r'(?:prefer|nice\s+to|bonus|benefit|we\s+offer)', line):
            in_requirements = False

        weight = 1.5 if in_requirements else 1.0

        for word in re.findall(r'\b[a-z]{3,}\b', line):
            if word not in _STOP_WORDS:
                words[word] = max(words.get(word, 0), weight)

    return words


# ---------------------------------------------------------------------------
# Composite semantic scorer
# ---------------------------------------------------------------------------

def compute_text_semantic_score(
    applicant: dict[str, Any],
    job: dict[str, Any],
) -> tuple[float, str]:
    """
    Compute a semantic alignment score (0–100) from deep text analysis.

    Components (weighted):
      1. Skills overlap (30%): shared skills / job required skills
      2. Job family similarity (20%): trade family match/adjacency
      3. Requirements fit (25%): experience years, education, certifications
      4. Experience text relevance (15%): weighted keyword matching
      5. Intent alignment (10%): career goals vs job title/description

    Returns (score, rationale_string).
    """
    job_skills = extract_job_skills(job)
    app_skills = extract_applicant_skills(applicant)
    app_family = applicant.get("canonical_job_family_code")
    job_family = job.get("canonical_job_family_code")

    details = []

    # --- 1. Skills overlap (weight: 0.30) ---
    if job_skills:
        overlap = job_skills & app_skills
        overlap_ratio = len(overlap) / len(job_skills)
        if overlap:
            bonus = min(10.0, len(overlap) * 3.0)
            skills_score = min(100.0, overlap_ratio * 90.0 + bonus)
        else:
            skills_score = 15.0
        details.append(f"skills={skills_score:.0f} ({len(overlap)}/{len(job_skills)})")
    else:
        skills_score = 50.0
        details.append("skills=50 (none extracted)")

    # --- 2. Job family similarity (weight: 0.20) ---
    from .normalizer import JOB_FAMILY_ADJACENCY
    if app_family and job_family:
        if app_family == job_family:
            family_score = 100.0
        elif job_family in JOB_FAMILY_ADJACENCY.get(app_family, set()):
            family_score = 65.0
        else:
            family_score = 10.0
    else:
        family_score = 40.0
    details.append(f"family={family_score:.0f}")

    # --- 3. Requirements fit (weight: 0.25) ---
    job_text = " ".join(filter(None, [
        job.get("description_raw"),
        job.get("requirements_raw"),
        job.get("preferred_qualifications_raw"),
    ]))
    req_scores = []

    job_years = _parse_experience_years(job_text) if job_text else None
    app_years = _estimate_applicant_experience_years(applicant)
    if job_years is not None and app_years is not None:
        if app_years >= job_years:
            req_scores.append(100.0)
        elif app_years >= job_years - 1:
            req_scores.append(70.0)
        else:
            deficit = job_years - app_years
            req_scores.append(max(10.0, 60.0 - deficit * 15.0))
    elif job_years is not None:
        req_scores.append(40.0)

    job_edu = _parse_education_level(job_text) if job_text else None
    app_edu = _estimate_applicant_education(applicant)
    edu_rank = {"high_school": 1, "military": 2, "trade_cert": 3, "associates": 4, "bachelors": 5}
    if job_edu and app_edu:
        job_r = edu_rank.get(job_edu, 2)
        app_r = edu_rank.get(app_edu, 2)
        if app_r >= job_r:
            req_scores.append(95.0)
        elif app_r >= job_r - 1:
            req_scores.append(65.0)
        else:
            req_scores.append(25.0)
    elif job_edu:
        req_scores.append(50.0)

    job_certs = _parse_certifications_required(job_text) if job_text else []
    if job_certs:
        app_text = " ".join(filter(None, [
            applicant.get("experience_raw"),
            applicant.get("bio_raw"),
            applicant.get("program_name_raw"),
        ])).lower()
        matched = sum(1 for c in job_certs if any(kw in app_text for kw in c.lower().split()))
        if matched == len(job_certs):
            req_scores.append(95.0)
        elif matched > 0:
            req_scores.append(40.0 + (matched / len(job_certs)) * 50.0)
        else:
            req_scores.append(20.0)

    requirements_score = sum(req_scores) / len(req_scores) if req_scores else 55.0
    details.append(f"reqs={requirements_score:.0f}")

    # --- 4. Experience text relevance (weight: 0.15) ---
    job_words = _extract_meaningful_words(job_text)
    app_text = " ".join(filter(None, [
        applicant.get("experience_raw"),
        applicant.get("internship_details"),
        applicant.get("essay_background"),
        applicant.get("bio_raw"),
    ]))
    app_words = _extract_meaningful_words(app_text)

    if job_words and app_words:
        common = set(job_words.keys()) & set(app_words.keys())
        if common:
            weighted_overlap = sum(job_words[w] * app_words[w] for w in common)
            max_possible = sum(v * 1.5 for v in job_words.values())
            ratio = weighted_overlap / max_possible if max_possible else 0
            exp_score = min(100.0, ratio * 180.0)
        else:
            exp_score = 15.0
    else:
        exp_score = 40.0
    details.append(f"exp={exp_score:.0f}")

    # --- 5. Intent alignment (weight: 0.10) ---
    career_goals = (applicant.get("career_goals_raw") or "").lower()
    job_title = (job.get("title_raw") or "").lower()
    job_desc_short = (job.get("description_raw") or "")[:500].lower()

    if career_goals and (job_title or job_desc_short):
        goal_words = set(re.findall(r'\b[a-z]{4,}\b', career_goals)) - _STOP_WORDS
        title_words = set(re.findall(r'\b[a-z]{4,}\b', job_title)) - _STOP_WORDS
        desc_words = set(re.findall(r'\b[a-z]{4,}\b', job_desc_short)) - _STOP_WORDS

        title_overlap = goal_words & title_words
        desc_overlap = goal_words & desc_words
        if title_overlap:
            intent_score = min(100.0, 60.0 + len(title_overlap) * 15.0)
        elif desc_overlap:
            intent_score = min(85.0, 40.0 + len(desc_overlap) * 5.0)
        else:
            intent_score = 25.0
    else:
        intent_score = 50.0
    details.append(f"intent={intent_score:.0f}")

    # --- Composite ---
    total = (
        skills_score * 0.30 +
        family_score * 0.20 +
        requirements_score * 0.25 +
        exp_score * 0.15 +
        intent_score * 0.10
    )
    total = round(min(100.0, max(0.0, total)), 2)

    rationale = f"text semantic: {', '.join(details)}"
    return total, rationale
