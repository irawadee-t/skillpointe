"""
extract.py — Post-process raw job descriptions into structured fields.

Different career sites dump the same information using slightly different
section headings (Southwire: "Required Education & Experience"; GE Vernova:
"Qualifications/Requirements"; Schneider: "What you'll do"; etc.). Rather than
duplicate logic per adapter, every adapter returns a `ScrapedJob` with a raw
`description` blob, and this module splits it into:

    description_raw        — the lead summary / overview
    responsibilities_raw   — duties / "What you'll do" / accountabilities
    requirements_raw       — required experience, education, certs
    qualifications_raw     — preferred / nice-to-haves
    pay_raw                — first pay-band string extracted from anywhere
    experience_level       — entry / mid / senior / lead (heuristic)

Pure functions, no I/O. Unit-tested.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Section headings — what each "bucket" recognises across the 5 employer sites
# ---------------------------------------------------------------------------

_RESP = re.compile(
    r"^\s*(?:"
    r"what\s+you[' ]ll\s+(?:do|be doing|accomplish)|"
    r"key\s+responsibilit\w+|"
    r"responsibilit\w+|"
    r"duties(?:\s+and\s+responsibilit\w+)?|"
    r"accountabilities|"
    r"job\s+duties|"
    r"essential\s+(?:functions|duties|job\s+functions)|"
    r"your\s+role|"
    r"position\s+responsibilit\w+|"
    r"day[- ]to[- ]day"
    r")\s*[:\-—]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_REQ = re.compile(
    r"^\s*(?:"
    r"required(?:\s+(?:skills|experience|qualification\w*|education(?:\s+(?:&|and)\s+experience)?))?|"
    r"requirements?|"
    r"must\s+haves?|"
    r"basic\s+qualifications|"
    r"minimum\s+(?:qualifications|requirements?)|"
    r"what\s+you\s+(?:need|bring|have)|"
    r"who\s+you\s+are"
    r")\s*[:\-—]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_PREFERRED = re.compile(
    r"^\s*(?:"
    r"preferred(?:\s+(?:skills|experience|qualification\w*|education(?:\s+(?:&|and)\s+experience)?))?|"
    r"nice\s+to\s+have|"
    r"desired\s+(?:skills|qualifications)|"
    r"bonus(?:\s+points)?|"
    r"additional\s+qualifications|"
    r"qualifications"          # generic "Qualifications" → treat as preferred
    r")\s*[:\-—]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_OVERVIEW = re.compile(
    r"^\s*(?:"
    r"job\s+(?:summary|description|overview|purpose)|"
    r"position\s+(?:summary|overview|description|purpose)|"
    r"about\s+(?:the\s+)?(?:role|position|job|opportunity)|"
    r"role\s+(?:summary|overview|description)|"
    r"overview|summary|"
    r"what\s+(?:we'?re\s+)?looking\s+for"
    r")\s*[:\-—]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Sections we always drop (boilerplate that adds no signal).
_DROP = re.compile(
    r"^\s*(?:"
    r"benefits(?:\s+we\s+offer)?|"
    r"compensation\s+(?:&|and)\s+benefits|"
    r"perks|"
    r"why\s+(?:work\s+(?:with|at|for)|join)|"
    r"about\s+(?:us|southwire|ball|ge\s+vernova|schneider|delta|ford)|"
    r"equal\s+(?:employment\s+)?opportunity|"
    r"eeo|"
    r"diversity(?:\s+(?:&|and)\s+inclusion)?|"
    r"nearest\s+major\s+market|"
    r"apply\s+now"
    r")\s*[:\-—]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Experience-level + pay heuristics
# ---------------------------------------------------------------------------

_PAY_RE = re.compile(
    r"\$\s?[\d,]+(?:\.\d{1,2})?"
    r"(?:\s?(?:k|K)\b|\s?(?:per\s+hour|/\s?hour|/\s?hr|hourly|an\s+hour|annual|annually|/\s?year|/\s?yr|a\s+year)?)?"
    r"(?:\s*[-–to]+\s*\$?\s?[\d,]+(?:\.\d{1,2})?"
    r"(?:\s?(?:k|K)\b|\s?(?:per\s+hour|/\s?hour|/\s?hr|hourly|an\s+hour|annual|annually|/\s?year|/\s?yr|a\s+year)?)?)?",
)

_LEVEL_HINTS: list[tuple[str, re.Pattern[str]]] = [
    # Order matters: more specific first.
    ("senior",  re.compile(r"\b(?:senior|sr\.?|lead|principal|staff)\b", re.I)),
    ("entry",   re.compile(r"\b(?:entry[- ]?level|apprentice|trainee|helper|intern|junior|jr\.?|i\b|level\s*1)\b", re.I)),
    ("mid",     re.compile(r"\b(?:journeyman|mid[- ]?level|experienced|ii|iii|level\s*2|level\s*3)\b", re.I)),
]
_YEARS_RE = re.compile(r"\b(\d{1,2})\+?\s*(?:to\s+\d{1,2}\s*)?years?\b", re.I)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParsedDescription:
    description: Optional[str] = None
    responsibilities: Optional[str] = None
    requirements: Optional[str] = None
    qualifications: Optional[str] = None
    pay_raw: Optional[str] = None
    experience_level: Optional[str] = None


# Generic boilerplate / UI-chrome strippers — apply to every scraped
# description before section-splitting so the worker UI gets clean copy.
_APPLY_CHROME_RE = re.compile(
    r"^(?:"
    r"apply\s+now(?:\s+»)?|"
    r"ans[øo]g\s+nu(?:\s+»)?|"
    r"start\s+ans[øo]gning(?:\s+med\s+linkedin)?|"
    r"start\s+application(?:\s+with\s+linkedin)?|"
    r"start|"
    r"please\s+wait\.\.\.|"
    r"vent\s+venligst\.\.\.|"
    r"loading\.\.\."
    r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Common boilerplate lead-in paragraphs (company history / values) that add
# zero signal. We trim the FIRST paragraph if it starts with one of these.
_BOILERPLATE_LEAD_PATTERNS = [
    # Ball
    re.compile(r"^at\s+ball\s*,\s*integrity\s+and\s+trust", re.I),
    re.compile(r"^at\s+ball\s*,\s*we\b", re.I),
    re.compile(r"^further\s+your\s+career\s+at\s+ball", re.I),
    re.compile(r"^ball\s+is\s+thrilled\s+to\s+receive", re.I),
    re.compile(r"^do\s+you\s+want\s+to\s+work\s+for\s+a\s+world[- ]leading\s+manufacturer", re.I),
    re.compile(r"^join\s+us\s*,\s*and\s+build\s+your\s+career", re.I),
    re.compile(r"^we\s+are\s+a\s+global\s+leader\s+in\s+sustainable", re.I),
    re.compile(r"^this\s+position\s+will\s+be\s+posted\s+for\s+a\s+minimum", re.I),
    # Southwire
    re.compile(r"^a\s+leader\s+in\s+technology\s+and\s+innovation\s*,\s*southwire", re.I),
    re.compile(r"^southwire\s+(?:and|company)", re.I),
    re.compile(r"^the\s+company\s+also\s+offers\s+digital\s+solutions", re.I),
    re.compile(r"^we\s+are\s+proud\s+to\s+offer\s+competitive", re.I),
    re.compile(r"^our\s+more\s+than\s+seven\s+decades", re.I),
    re.compile(r"^how\s+will\s+you\s+power\s+what['']s\s+possible", re.I),
    # Schneider
    re.compile(r"^schneider['']s\s+purpose", re.I),
    re.compile(r"^do\s+you\s+dream\s+of\s+working\s+in\s+a\s+company", re.I),
    re.compile(r"^great\s+people\s+make\s+schneider\s+electric", re.I),
    re.compile(r"^schneider\s+electric\s+is\s+looking", re.I),
    # Delta
    re.compile(r"^working\s+at\s+delta", re.I),
    re.compile(r"^at\s+delta\s+air\s+lines", re.I),
    re.compile(r"^how\s+you['']ll\s+help\s+us\s+keep\s+climbing", re.I),
    # GE Vernova
    re.compile(r"^at\s+ge\s+vernova", re.I),
    re.compile(r"^ge\s+vernova\s+is\s+accelerating", re.I),
    # Ford
    re.compile(r"^at\s+ford\s+motor\s+company", re.I),
    re.compile(r"^we\s+are\s+the\s+movement\s+of\s+ideas", re.I),
    re.compile(r"^in\s+this\s+position\s*\.{2,3}\s*$", re.I),
]

# Site-header keys that get scraped into the description by SAP SuccessFactors
# templates (Date:, Company:, Location:, Req ID:, etc.).
_HEADER_KEY_RE = re.compile(
    r"^(?:date|company|location|job\s+category|req(?:uisition)?\s+id|posted|firma|lokalitet|jobkategori|kr[æa]vet\s+id):\s*$",
    re.IGNORECASE | re.MULTILINE,
)


_HEADER_NOISE_RE = re.compile(
    r"^("
    r"\s*$|"                                               # blank
    r".{0,60}\b(?:LLC|Inc\.?|Corp\.?|Corporation|GmbH|Ltd\.?|S\.A\.|Company)\s*$|"  # bare company name
    r"\d{1,2}\.?\s*\w{3,9}\.?\s*\d{2,4}$|"                # "11. jun. 2026" / "Jun 22, 2026"
    r"\w{3,9}\s+\d{1,2},?\s*\d{4}$|"                       # "Jun 22, 2026"
    r"\d{4}-\d{1,2}-\d{1,2}$|"                             # ISO date
    r"[A-Z][a-zA-Z .'\-]+,\s*[A-Z]{2}(?:,\s*US)?(?:,\s*\d{4,5})?$|"  # "Hawesville, KY, US, 42348"
    r"(?:Manufacturing|Departmental|Operations|Field Service)[^.\n]{0,40}$|"  # category header
    r"Req\.?\s*ID:?\s*\d+\s*$|"
    r"\d{4,8}\s*$"                                         # bare 5-7 digit ID
    r")",
    re.IGNORECASE,
)


def _strip_boilerplate(text: str) -> str:
    """Remove apply-button chrome, header-key lines, company-name / date /
    location header artifacts, and the most-common company-history lead
    paragraphs before section-splitting."""
    # Drop apply-button chrome lines anywhere in the text.
    text = _APPLY_CHROME_RE.sub("", text)
    text = _HEADER_KEY_RE.sub("", text)

    # Strip lines from the TOP that look like header artifacts (bare company
    # name, dates, "City, ST" lines, req IDs, blank). Stop at the first line
    # that looks like real prose (length > 60 OR ends in punctuation).
    lines = text.split("\n")
    while lines:
        first = lines[0].strip()
        if _HEADER_NOISE_RE.match(first):
            lines.pop(0); continue
        # Looks like real prose? keep it.
        if len(first) > 60 or first.endswith((".", "!", "?")):
            break
        # Otherwise it's a short non-prose line (likely a title or header) — drop.
        if first and len(first) < 60:
            lines.pop(0); continue
        break
    text = "\n".join(lines).strip()

    # Strip leading lines that match boilerplate lead patterns — line-based
    # (not paragraph-based) because some sites use single-newlines between
    # paragraphs, so a `\n\n` split would gobble the whole body.
    lines = text.split("\n")
    while lines:
        first = lines[0].strip()
        if first and any(pat.search(first) for pat in _BOILERPLATE_LEAD_PATTERNS):
            lines.pop(0)
            # Also skip following lines that are obvious continuations of the
            # boilerplate (start with lowercase, or are short fluff lines).
            continue
        break
    return "\n".join(lines).strip()


def parse_sections(text: Optional[str]) -> ParsedDescription:
    """Split a free-form job description into structured sections."""
    if not text or not text.strip():
        return ParsedDescription()
    text = text.replace("\r\n", "\n").strip()
    text = _strip_boilerplate(text)
    if not text:
        return ParsedDescription()

    # Split text into (heading-or-None, body) chunks.
    lines = text.split("\n")
    buckets: dict[str, list[str]] = {
        "description": [], "responsibilities": [], "requirements": [],
        "qualifications": [], "drop": [],
    }
    current = "description"

    for raw in lines:
        line = raw.strip()
        if not line:
            buckets[current].append("")
            continue

        # Heading detection — short, no terminal period.
        if len(line) <= 80 and not line.endswith("."):
            if _DROP.match(line):
                current = "drop"
                continue
            if _OVERVIEW.match(line):
                current = "description"
                continue
            if _RESP.match(line):
                current = "responsibilities"
                continue
            if _REQ.match(line):
                current = "requirements"
                continue
            if _PREFERRED.match(line):
                current = "qualifications"
                continue
        buckets[current].append(raw)

    def clean(bucket: str) -> Optional[str]:
        out = "\n".join(buckets[bucket]).strip()
        return out or None

    pay_raw = _first_pay_match(text)
    level = _infer_experience_level(text)

    return ParsedDescription(
        description=clean("description"),
        responsibilities=clean("responsibilities"),
        requirements=clean("requirements"),
        qualifications=clean("qualifications"),
        pay_raw=pay_raw,
        experience_level=level,
    )


def _first_pay_match(text: str) -> Optional[str]:
    # Prefer matches that contain a hyphen/range or a clear unit; fall back to
    # any dollar amount.
    candidates = _PAY_RE.findall(text)
    if not candidates:
        return None
    ranges = [c for c in candidates if "-" in c or "–" in c or "to" in c.lower()]
    return (ranges[0] if ranges else candidates[0]).strip()


def _infer_experience_level(text: str) -> Optional[str]:
    # Title-style entry signals win first — "Apprentice / Trainee / Helper /
    # Entry-Level" should NEVER be classified as senior even if the body text
    # mentions "10 years experience" describing the trade as a whole.
    first_line = text.split("\n", 1)[0]
    if re.search(r"\b(?:apprentice|trainee|helper|intern|entry[- ]?level|junior|jr\.?)\b", first_line, re.I):
        return "entry"
    if re.search(r"\b(?:senior|sr\.?|lead|principal|staff|master)\b", first_line, re.I):
        return "senior"

    # Years of experience is the next-strongest signal.
    years_matches = [int(m.group(1)) for m in _YEARS_RE.finditer(text)]
    if years_matches:
        y = max(years_matches)
        if y >= 7:
            return "senior"
        if y >= 3:
            return "mid"
        return "entry"
    for label, pat in _LEVEL_HINTS:
        if pat.search(text):
            return label
    return None
