"""
normalizer.py — deterministic normalization for applicants and jobs.

All functions are pure (no DB writes, no filesystem access).
The calling scripts supply reference data (job families, geography regions)
fetched from the DB.

Key functions:
  normalize_program_to_job_family  — program name → canonical family code
  normalize_job_title_to_family    — job title + career pathway → family code
  normalize_pay_range              — "$22/hr–$33/hr" → (22, 33, 'hourly')
  normalize_location               — state → region code
  normalize_timing                 — completion/availability dates → readiness
  normalize_work_setting           — raw work setting string → enum value

The JOB_FAMILY_ADJACENCY constant is also exported for use by gates.py and scorer.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any


# ---------------------------------------------------------------------------
# Job family adjacency map
# Symmetric: if A is adjacent to B, B is adjacent to A.
# Used for NEAR_FIT determination in gate + scoring.
# Based on the SPF trade families seeded in supabase/seed.sql.
# Admins can refine this via admin policy in a later phase.
# ---------------------------------------------------------------------------
JOB_FAMILY_ADJACENCY: dict[str, set[str]] = {
    "electrical":           {"construction", "hvac", "manufacturing"},
    "plumbing":             {"construction", "hvac"},
    "hvac":                 {"electrical", "plumbing", "construction"},
    "construction":         {"electrical", "plumbing", "hvac", "welding"},
    "welding":              {"construction", "manufacturing", "automotive"},
    "automotive":           {"welding", "manufacturing", "logistics"},
    "manufacturing":        {"welding", "automotive", "logistics"},
    "logistics":            {"automotive", "manufacturing"},
    "healthcare_support":   {"administrative"},
    "administrative":       {"healthcare_support", "it_support"},
    "it_support":           {"administrative"},
    "culinary":             set(),
    "childcare_education":  {"administrative"},
    "cosmetology":          set(),
    "security":             {"administrative"},
}


# ---------------------------------------------------------------------------
# Normalization result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class NormResult:
    family_code: str | None
    confidence: str          # 'high', 'medium', 'low'
    match_reason: str
    needs_review: bool = False
    alternative_families: list[str] = field(default_factory=list)


@dataclass
class TimingResult:
    months_to_available: int | None     # None = unknown
    readiness_label: str                # 'available_now', 'near_completion', 'in_progress', 'future', 'unknown'
    is_currently_enrolled: bool


# ---------------------------------------------------------------------------
# Program / job title → job family normalization
# ---------------------------------------------------------------------------

def normalize_program_to_job_family(
    program_name: str | None,
    job_families: list[dict[str, Any]],
) -> NormResult:
    """
    Map an applicant's raw program name to a canonical job family.

    job_families: rows from canonical_job_families table:
        [{id, code, name, aliases: [str], ...}]

    Strategy (in order):
      1. Exact match on code or name
      2. Alias substring match
      3. Keyword overlap scoring
      4. Return None + needs_review if no match
    """
    if not program_name or not program_name.strip():
        return NormResult(None, "low", "no program name", needs_review=True)

    name_lower = program_name.strip().lower()

    # 1. Exact match on code or display name
    for fam in job_families:
        if name_lower == fam["code"].lower() or name_lower == fam["name"].lower():
            return NormResult(fam["code"], "high", f"exact match: {fam['name']}")

    # 2. Alias match — check if any alias is contained in or contains the name
    matches: list[tuple[str, str]] = []
    for fam in job_families:
        aliases = fam.get("aliases") or []
        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower in name_lower or name_lower in alias_lower:
                matches.append((fam["code"], alias))
                break  # one alias per family

    if len(matches) == 1:
        code, alias = matches[0]
        return NormResult(code, "high", f"alias match: '{alias}'")

    if len(matches) > 1:
        codes = [m[0] for m in matches]
        return NormResult(
            codes[0], "medium",
            f"multiple alias matches: {codes[:3]}",
            needs_review=True,
            alternative_families=codes[1:],
        )

    # 3. Keyword overlap scoring
    best_code, best_score, best_reason = _keyword_overlap(name_lower, job_families)

    if best_score >= 2:
        confidence = "high" if best_score >= 3 else "medium"
        return NormResult(best_code, confidence, f"keyword overlap (score {best_score}): {best_reason}")

    if best_score >= 1:
        return NormResult(
            best_code, "low",
            f"weak keyword match: {best_reason}",
            needs_review=True,
        )

    return NormResult(None, "low", f"no match for: {program_name!r}", needs_review=True)


def normalize_job_title_to_family(
    title: str | None,
    career_pathway: str | None,
    job_families: list[dict[str, Any]],
) -> NormResult:
    """
    Map a job's title (and optional SPF career_pathway from extra data) to a canonical family.
    career_pathway is tried first — it is usually more specific and reliable.
    """
    # career_pathway is the SPF taxonomy role (e.g. "Electrician", "HVAC Technician")
    if career_pathway and career_pathway.strip():
        pathway_result = normalize_program_to_job_family(career_pathway, job_families)
        if pathway_result.family_code and pathway_result.confidence in ("high", "medium"):
            return NormResult(
                pathway_result.family_code,
                pathway_result.confidence,
                f"from career_pathway '{career_pathway}': {pathway_result.match_reason}",
                needs_review=pathway_result.needs_review,
            )

    # Fall back to job title
    title_result = normalize_program_to_job_family(title, job_families)
    if title_result.family_code:
        return NormResult(
            title_result.family_code,
            title_result.confidence,
            f"from title '{title}': {title_result.match_reason}",
            needs_review=title_result.needs_review,
        )

    return NormResult(None, "low", f"no match for title={title!r}, pathway={career_pathway!r}", needs_review=True)


def _keyword_overlap(name_lower: str, job_families: list[dict[str, Any]]) -> tuple[str | None, int, str]:
    """Return (best_family_code, best_score, best_reason) for keyword overlap."""
    best_code: str | None = None
    best_score = 0
    best_reason = ""

    for fam in job_families:
        score = 0
        matched_kws: list[str] = []
        sources = [fam["code"], fam["name"]] + (fam.get("aliases") or [])
        for src in sources:
            for word in re.split(r"[\s/,\-]+", src.lower()):
                if len(word) >= 4 and word in name_lower:
                    score += 1
                    matched_kws.append(word)
        if score > best_score:
            best_score = score
            best_code = fam["code"]
            best_reason = f"{fam['name']} (kw: {matched_kws[:3]})"

    return best_code, best_score, best_reason


# ---------------------------------------------------------------------------
# Pay range normalization
# ---------------------------------------------------------------------------

_PAY_RE_RANGE = re.compile(
    r"\$?([\d,]+(?:\.\d+)?)\s*(?:–|—|-|to)\s*\$?([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_PAY_RE_SINGLE = re.compile(r"\$?([\d,]+(?:\.\d+)?)", re.IGNORECASE)
_HOURLY_RE = re.compile(r"\bhr(ly)?\b|\bper\s+hour\b|/hr", re.IGNORECASE)
_ANNUAL_RE = re.compile(r"\bann(ual)?\b|\byear\b|\bsalary\b|\b/yr\b|\bpa\b", re.IGNORECASE)


def normalize_pay_range(pay_raw: str | None) -> tuple[float | None, float | None, str | None]:
    """
    Parse a raw pay string into (min, max, pay_type).

    pay_type: 'hourly', 'annual', or None.

    Examples:
      "$22/hr–$33/hr"              → (22.0, 33.0, 'hourly')
      "$45,000 – $65,000 annually" → (45000.0, 65000.0, 'annual')
      "$28/hr"                     → (28.0, 28.0, 'hourly')
    """
    if not pay_raw:
        return None, None, None

    pay_type: str | None = None
    if _HOURLY_RE.search(pay_raw):
        pay_type = "hourly"
    elif _ANNUAL_RE.search(pay_raw):
        pay_type = "annual"

    # Try range pattern first
    m = _PAY_RE_RANGE.search(pay_raw)
    if m:
        lo = float(m.group(1).replace(",", ""))
        hi = float(m.group(2).replace(",", ""))
        if pay_type is None:
            pay_type = "hourly" if max(lo, hi) < 500 else "annual"
        return lo, hi, pay_type

    # Single value
    m = _PAY_RE_SINGLE.search(pay_raw)
    if m:
        val = float(m.group(1).replace(",", ""))
        if pay_type is None:
            pay_type = "hourly" if val < 500 else "annual"
        return val, val, pay_type

    return None, None, None


# ---------------------------------------------------------------------------
# Location / geography normalization
# ---------------------------------------------------------------------------

def normalize_location(
    city: str | None,
    state: str | None,
    geography_regions: list[dict[str, Any]],
) -> str | None:
    """
    Map a US state code to a regional code using the geography_regions table.

    geography_regions: rows from geography_regions table:
        [{code, name, states: [str], ...}]

    Returns the region code (e.g. 'midwest') or None if not found.
    """
    if not state:
        return None

    state_upper = state.strip().upper()
    for region in geography_regions:
        states = region.get("states") or []
        if state_upper in [s.upper() for s in states]:
            return region["code"]
    return None


# ---------------------------------------------------------------------------
# Timing / readiness normalization
# ---------------------------------------------------------------------------

def normalize_timing(
    expected_completion_date: date | None,
    available_from_date: date | None,
    today: date | None = None,
) -> TimingResult:
    """
    Determine readiness from timing fields.

    Uses available_from_date preferentially (explicitly declared availability),
    then expected_completion_date (end of program → when applicant becomes available).

    Readiness labels:
      'available_now'   — date is in the past or today
      'near_completion' — < 4 months out
      'in_progress'     — 4–12 months out
      'future'          — > 12 months out
      'unknown'         — no dates provided
    """
    if today is None:
        today = date.today()

    ref_date = available_from_date or expected_completion_date
    if ref_date is None:
        return TimingResult(None, "unknown", False)

    if ref_date <= today:
        return TimingResult(0, "available_now", False)

    delta_days = (ref_date - today).days
    months = delta_days // 30
    is_enrolled = True  # has a future completion date → currently enrolled

    if months < 4:
        label = "near_completion"
    elif months <= 12:
        label = "in_progress"
    else:
        label = "future"

    return TimingResult(months, label, is_enrolled)


# ---------------------------------------------------------------------------
# Work setting normalization
# ---------------------------------------------------------------------------

_WORK_SETTING_CANONICAL = {
    "on_site":          "on_site",
    "onsite":           "on_site",
    "in_person":        "on_site",
    "in-person":        "on_site",
    "no":               "on_site",   # SkillPointe Remote_Status="No"
    "hybrid":           "hybrid",
    "flexible":         "flexible",
    "remote":           "remote",
    "yes":              "remote",    # Remote_Status="Yes"
    "fully_remote":     "remote",
    "fully remote":     "remote",
    "work_from_home":   "remote",
    "wfh":              "remote",
}


def normalize_work_setting(raw: str | None) -> str | None:
    """Normalise work_setting strings to canonical enum values."""
    if not raw:
        return None
    return _WORK_SETTING_CANONICAL.get(raw.strip().lower().replace("-", "_"))
