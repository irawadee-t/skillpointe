"""Seniority ontology — evidence-based classification of job preparation level.

Grounded in O*NET's Job Zone framework (onetcenter.org), which grades
occupations by required education, related experience, and on-the-job
training. Collapsed to the four levels that matter for skilled-trades
hiring, with an explicit Job Zone analogue:

  entry       Zone 1-2: little/some preparation. Helper, trainee, apprentice,
              "no experience necessary", "will train", <= 1 year asked.
  mid         Zone 3: medium preparation. Certificate/apprenticeship complete,
              journeyman-track, 2-4 years asked.
  senior      Zone 4: considerable preparation. Lead/master-level craft,
              5+ years asked.
  management  Supervisory ladder (foreman, superintendent, manager) — a
              DIFFERENT ladder from craft seniority, not a rung above it.

Design rules:
  * The classifier reads what the posting actually SAYS — title cues, an
    explicit years-of-experience ask, and entry-friendly phrases — and returns
    the evidence for every decision, so a label is always explainable.
  * Explicit trainability ("no experience required", "we will train") beats a
    mid-looking title: employers who say they will train mean it.
  * A stated years requirement beats title vibes in the other direction:
    "Technician" asking 7+ years is senior work whatever the title implies.
  * Everything is pure and deterministic. No I/O, no model calls.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Signal vocabularies
# ---------------------------------------------------------------------------

_ENTRY_TITLE = re.compile(
    r"\b(apprentice|helper|trainee|entry[ -]level|junior|jr\.?|intern(ship)?|"
    r"assembler|laborer|general labor|associate technician|tech(nician)?\s+i\b|"
    r"level\s+1|starter|beginner|new grad(uate)?s?)\b",
    re.IGNORECASE,
)
_SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|lead|master|principal|specialist\s+iii|tech(nician)?\s+"
    r"(iii|iv|3|4)\b|level\s+(3|4|iii|iv)|journey(man|person)\s+lead|expert)\b",
    re.IGNORECASE,
)
_MGMT_TITLE = re.compile(
    r"\b(manager|supervisor|superintendent|foreman|forewoman|director|"
    r"chief|head\s+of|general\s+manager)\b",
    re.IGNORECASE,
)
_MID_TITLE = re.compile(
    r"\b(journey(man|person)|tech(nician)?\s+(ii|2)\b|level\s+(2|ii)\b|"
    r"licensed|certified\s+\w+\s+(technician|mechanic|installer))\b",
    re.IGNORECASE,
)

# "no experience necessary", "will train", tuition/paid training programs.
_ENTRY_FRIENDLY = re.compile(
    r"(no (prior |previous )?experience (is )?(necessary|needed|required)|"
    r"we('ll| will) train|willing to train|paid training|on[- ]the[- ]job training|"
    r"training (is )?provided|no experience\? no problem|"
    r"recent graduates?( are)? (welcome|encouraged)|entry[ -]level opportunity|"
    r"earn while you learn|apprenticeship program)",
    re.IGNORECASE,
)

# "3+ years", "three (3) years", "minimum of 5 years", "2-4 years"
# "3+ years of X Y experience" — up to three qualifier words may sit between
# "years of" and "experience" ("industrial maintenance", "MIG welding", ...).
_YEARS = re.compile(
    r"(?:minimum of\s+|at least\s+|requires?\s+)?(\d{1,2})\s*(?:\+|-\s*\d{1,2})?\s*"
    r"(?:or more\s+)?years?[' ]*(?:of\s+)?(?:[\w/-]+\s+){0,3}?(?:experience|exp\b)",
    re.IGNORECASE,
)
_WORDY_YEARS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_WORDY_YEARS_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:\(\d+\)\s*)?"
    r"years?[' ]*(?:of\s+)?(?:\w+\s+){0,3}?experience",
    re.IGNORECASE,
)


@dataclass
class SeniorityResult:
    level: str                       # entry | mid | senior | management
    job_zone: str                    # O*NET analogue: "1-2" | "3" | "4" | "supervisory"
    years_required: int | None
    entry_friendly: bool
    evidence: list[str] = field(default_factory=list)


_ZONE = {"entry": "1-2", "mid": "3", "senior": "4", "management": "supervisory"}


def extract_years_required(text: str) -> int | None:
    """The highest explicit years-of-experience ask in the text, if any."""
    best: int | None = None
    for m in _YEARS.finditer(text):
        n = int(m.group(1))
        if n <= 40 and (best is None or n > best):
            best = n
    for m in _WORDY_YEARS_RE.finditer(text):
        n = _WORDY_YEARS[m.group(1).lower()]
        if best is None or n > best:
            best = n
    return best


def classify_seniority(
    title: str | None,
    description: str | None = None,
    requirements: str | None = None,
) -> SeniorityResult:
    """Classify a posting's preparation level from its own words."""
    title = title or ""
    body = " ".join(t for t in (description, requirements) if t)
    evidence: list[str] = []

    years = extract_years_required(f"{title} {body}")
    if years is not None:
        evidence.append(f"asks for {years}+ years of experience")

    friendly = bool(_ENTRY_FRIENDLY.search(body) or _ENTRY_FRIENDLY.search(title))
    if friendly:
        m = _ENTRY_FRIENDLY.search(body) or _ENTRY_FRIENDLY.search(title)
        evidence.append(f'posting says "{m.group(0).strip()}"')

    # Management is its own ladder: a supervisory title decides immediately.
    if _MGMT_TITLE.search(title):
        evidence.append(f"supervisory title: {_MGMT_TITLE.search(title).group(0)}")
        return SeniorityResult("management", _ZONE["management"], years, friendly, evidence)

    # Explicit trainability wins for the craft ladder — employers who say
    # they will train are describing an entry job whatever the title hints.
    if friendly and (years is None or years <= 1):
        return SeniorityResult("entry", _ZONE["entry"], years, True, evidence)

    # A stated years ask is the strongest remaining signal (O*NET grades
    # zones chiefly by related experience required).
    if years is not None:
        if years >= 5:
            level = "senior"
        elif years >= 2:
            level = "mid"
        else:
            level = "entry"
        return SeniorityResult(level, _ZONE[level], years, friendly, evidence)

    # Title cues, strongest first.
    if _SENIOR_TITLE.search(title):
        evidence.append(f"senior-craft title: {_SENIOR_TITLE.search(title).group(0)}")
        return SeniorityResult("senior", _ZONE["senior"], None, friendly, evidence)
    if _ENTRY_TITLE.search(title):
        evidence.append(f"entry title: {_ENTRY_TITLE.search(title).group(0)}")
        return SeniorityResult("entry", _ZONE["entry"], None, friendly, evidence)
    if _MID_TITLE.search(title):
        evidence.append(f"skilled-craft title: {_MID_TITLE.search(title).group(0)}")
        return SeniorityResult("mid", _ZONE["mid"], None, friendly, evidence)

    # Nothing decisive: the honest default for trade postings is entry-adjacent
    # mid ("some preparation"), flagged with no evidence so callers can treat
    # it as low confidence.
    evidence.append("no explicit signals; defaulted")
    return SeniorityResult("mid", _ZONE["mid"], None, friendly, evidence)
