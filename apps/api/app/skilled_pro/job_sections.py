"""
job_sections.py — Normalize scraped job text into a fixed display schema.

Scraped descriptions arrive as messy dumps: bullets snapped mid-word ("At
least 2 year" / "s" / "of experience…"), pay fragmented across lines ("The pay
for this position is $" / "27.68" / "per hour."), inline "·" separator runs
that were never split, question-form headings ("What will you do?"), and
paragraphs of corporate marketing + EEO legalese mixed into requirements.

This module turns any combination of the raw fields into one canonical schema:

    {"about": [...], "duties": [...], "needs": [...], "nice_to_have": [...],
     "benefits": [...], "schedule": [...], "company": [...], "notices": [...],
     "facts": {"shift", "pay_text", "location_text"},
     "quality": "good" | "messy"}

Canonical taxonomy (enforced):
  about        role-relevant prose only
  duties       task bullets ("What you'll do")
  needs        requirement bullets ("What you'll need")
  nice_to_have preferred qualifications
  benefits     pay context + real benefits content ("Pay & benefits")
  schedule     shifts / hours / days
  company      mission / values / marketing prose (collapsed in the UI)
  notices      EEO, drug screen, legal disclaimers, benefit-plan sponsor
               legalese (collapsed in the UI)

Guarantees:
  * Fully deterministic — no I/O, no LLM, unit-tested against real scrapes.
  * Extractive only: the output vocabulary is a subset of the input (plus
    nothing) — content is never invented.
  * Nothing is silently deleted: every source line lands in exactly one
    bucket. The only drops are (a) exact/near-exact repeats, (b) bare
    restatements of the structured pay fact (captured into facts.pay_text),
    (c) structural header labels, and (d) known scraper UI chrome.

`parse_job_sections` is the floor. When it flags the result "messy", callers
may invoke `llm_reorganize_sections` — a single bounded LLM call that only
REORGANIZES the provided text (never rewrites facts), is post-validated to be
extractive, and falls back to the deterministic result on any failure.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re

logger = logging.getLogger(__name__)

SECTION_KEYS = (
    "about", "duties", "needs", "nice_to_have", "benefits",
    "schedule", "company", "notices",
)

# Buckets where content stays put once a header established the context.
_STICKY_BUCKETS = frozenset(
    {"duties", "needs", "nice_to_have", "benefits", "schedule", "company", "notices"}
)

# ---------------------------------------------------------------------------
# Header patterns → target bucket
# ---------------------------------------------------------------------------

_HEADER_BUCKETS: list[tuple[re.Pattern[str], str]] = [
    # nice_to_have BEFORE needs: "preferred qualifications" must not hit the
    # generic "qualifications" pattern.
    (
        re.compile(
            r"^(?:preferred(?:\s+(?:education\s*(?:&|and)\s*experience|skills?|experience|"
            r"qualifications?))?|nice\s+to\s+have|desired\s+(?:skills?|qualifications?)|"
            r"bonus(?:\s+(?:points|skills?|qualifications?))?|additional\s+qualifications?|"
            r"even\s+better,?\s+you\s+may\s+have\.{0,3})$",
            re.IGNORECASE,
        ),
        "nice_to_have",
    ),
    (
        re.compile(
            r"^(?:general\s+requirements?|requirements?|required(?:\s+(?:education\s*(?:&|and)\s*"
            r"experience|skills?|experience|qualifications?))?|minimum\s+(?:requirements?|"
            r"qualifications?)|basic\s+qualifications?|qualifications?|must\s+haves?|"
            r"what\s+you(?:'ll|\s+will)\s+need|what\s+you\s+(?:need|bring)|"
            r"what\s+you\s+need\s+to\s+succeed|education|"
            r"education\s*(?:&|and)\s*experience|who\s+you\s+are|"
            r"what\s+qualifications?(?:\s+will\s+make\s+you\s+successful)?|"
            r"this\s+job\s+might\s+be\s+for\s+you\s+if|"
            r"physical(?:\s*/\s*environmental|\s+and\s+environmental)?\s+demands?)$",
            re.IGNORECASE,
        ),
        "needs",
    ),
    (
        re.compile(
            r"^(?:primary\s+job\s+(?:tasks?|duties)|(?:key\s+|your\s+|position\s+)?"
            r"responsibilit(?:y|ies)|duties(?:\s+and\s+responsibilit(?:y|ies))?|job\s+duties|"
            r"essential\s+(?:functions?|duties|job\s+functions?)|"
            r"what\s+(?:will\s+you\s+do|you(?:'ll|\s+will)\s+(?:do|be\s+doing))|"
            r"accountabilities|day[- ]to[- ]day|"
            r"a\s+typical\s+day|cross[- ]?training|quality|safety)$",
            re.IGNORECASE,
        ),
        "duties",
    ),
    (
        re.compile(
            r"^(?:benefits(?:\s+we\s+offer)?|what\s+we\s+(?:offer|provide)|perks|"
            r"rate\s+of\s+pay(?:\s+and\s+benefits)?|pay\s*(?:&|and)\s*benefits|total\s+rewards|"
            r"compensation(?:\s*(?:&|and)\s*benefits)?|what(?:'s|\s+is)\s+in\s+it\s+for\s+you)$",
            re.IGNORECASE,
        ),
        "benefits",
    ),
    (
        re.compile(
            r"^(?:work\s+)?schedule|shift\s+(?:details?|information|schedule)|hours\s+of\s+work$",
            re.IGNORECASE,
        ),
        "schedule",
    ),
    (
        re.compile(
            r"^(?:about\s+us|who\s+we\s+are|why\s+(?:join|work)(?:\s+.*)?|(?:the\s+)?company|"
            r"about\s+(?:the\s+|our\s+)?company|our\s+(?:story|culture|values|mission)|"
            r"looking\s+to\s+make\s+an\s+impact(?:\s+.*)?)$",
            re.IGNORECASE,
        ),
        "company",
    ),
    (
        re.compile(
            r"^(?:equal\s+(?:employment\s+)?opportunity(?:\s+employer)?(?:\s+statement)?|"
            r"eeo(?:\s+statement)?|legal\s+notices?|disclaimers?)$",
            re.IGNORECASE,
        ),
        "notices",
    ),
    (
        re.compile(
            r"^(?:about\s+(?:the\s+)?(?:role|position|job|opportunity)|"
            r"job\s+(?:overview|summary|description|purpose)|"
            r"position\s+(?:overview|summary|description|purpose)|overview|summary|"
            r"role\s+(?:overview|summary|description)|"
            r"how\s+you(?:'ll|\s+will)\s+help\s+us(?:\s+.*)?)$",
            re.IGNORECASE,
        ),
        "about",
    ),
]

# Unknown header labels ("SKILL (Education, Experience…)", "CLASSES IN:") are
# routed by keyword. Order matters: first hit wins.
_HEADER_KEYWORD_BUCKETS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"responsib|duties|task|function", re.IGNORECASE), "duties"),
    (re.compile(r"skill|education|experience|qualification|demand|effort|class", re.IGNORECASE),
     "needs"),
    (re.compile(r"benefit|compensation|reward|pay", re.IGNORECASE), "benefits"),
    (re.compile(r"schedule|shift|hours", re.IGNORECASE), "schedule"),
    (re.compile(r"summary|overview|about", re.IGNORECASE), "about"),
]

# Leading bullet / numbering decoration to strip off a line. A hyphen followed
# by an amount is a snapped pay range ("$27.14" / "- $28.40"), not a bullet.
_BULLET_PREFIX = re.compile(r"^\s*(?:-(?!\s*[$€£\d])|[•·▪►◆★✓✔*o]|\d{1,2}[.)]|[a-z][.)])\s+")

# "Label: value" fact lines that duplicate structured columns.
_FACT_PATTERNS: dict[str, re.Pattern[str]] = {
    "location_text": re.compile(r"^location\s*[:\-—]\s*(.+)$", re.IGNORECASE),
    "shift": re.compile(r"^shift\s*[:\-—]\s*(.+)$", re.IGNORECASE),
    "pay_text": re.compile(r"^pay\s*(?:rate|range)?\s*[:\-—]\s*(.+)$", re.IGNORECASE),
}

# Lines classified as requirements ("needs").
_NEEDS_LINE = re.compile(
    r"^(?:must\b|ability\s+to\b|able\s+to\b|experience\b|\d+[-+]?\d*\+?\s+years?\b|knowledge\b|"
    r"certified\b|certification\b|license[d]?\b|licence\b|diploma\b|high\s school\b|ged\b|"
    r"bachelor|associate'?s?\b|degree\b|willing(?:ness)?\s+to\b|proficien|familiar(?:ity)?\s+with\b|"
    r"strong\b|excellent\b|bilingual\b|valid\b|minimum\b|prior\s+experience\b|"
    r"authorized\s+to\s+work\b|requires?\b|good\s+understanding\b|expertise\s+with\b|"
    r"at\s+least\b|high\s+school\b)",
    re.IGNORECASE,
)

# Mega-line handling: scraped blobs sometimes arrive as ONE huge line with
# double-space item separators and inline ALL-CAPS headers ("POSITION SUMMARY:",
# "SKILL (Education, ...)"). Explode those so the normal pipeline can work.
_MEGALINE_MIN = 300
_MULTISPACE_SPLIT = re.compile(r"\s{2,}")
_INLINE_CAPS_HEADER_SPLIT = re.compile(
    r"(?<=[.a-z0-9)’])\s+"
    r"(?=(?:[A-Z]{2,}(?:\s+[A-Z]{2,}){0,3})\s*(?::|\([^)]{0,100}\)))"
)

# Imperative verbs that open a responsibility bullet.
_DUTY_VERBS = (
    "load|unload|operate|maintain|assist|receive|perform|inspect|clean|monitor|report|follow|"
    "use|utilize|properly|complete|prepare|support|conduct|ensure|review|change|make|layer|"
    "troubleshoot|repair|install|remove|move|lift|carry|drive|weld|assemble|build|package|"
    "stack|record|document|communicate|coordinate|collaborate|train|learn|attend|adhere|comply|"
    "work|read|verify|test|measure|cut|set\\s+up|start|stop|adjust|feed|label|tag|wear|observe|"
    "diagnose|changes|maintains|"
    "immediately|do\\s+not|will\\b|responsible\\b|provide|manage|lead|develop|help|handle|keep|stock"
)
_DUTY_LINE = re.compile(rf"^(?:{_DUTY_VERBS})\b", re.IGNORECASE)

# Benefits keywords for stray benefit content outside a Benefits header.
_BENEFIT_LINE = re.compile(
    # NOTE: "vision" only counts with insurance context — "Welder Vision
    # requirements" is a requirement, not a benefit.
    r"\b(?:401\s*\(?k\)?|dental|vision\s+(?:insurance|coverage|plan)|"
    r"medical,?\s+dental,?\s+(?:and\s+)?vision|"
    r"medical\s+insurance|paid\s+time\s+off|pto\b|"
    r"tuition\s+(?:reimbursement|assistance)|life\s+insurance|parental\s+leave|"
    r"employee\s+discount|retirement\s+(?:plan|benefits)|benefits\s+include|"
    r"relocation\s+assistance|paid\s+holidays|disability\s+(?:insurance|benefits)|"
    r"health\s*care\s+benefits|healthcare\s+benefits|annual\s+vacation|"
    r"weeks?\s+of\s+(?:annual\s+)?vacation)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Content-cue patterns (deterministic classification). Conservative: a line
# with no cue stays in About the role rather than being dropped or guessed.
# ---------------------------------------------------------------------------

# EEO / legal / compliance boilerplate → notices.
_NOTICE_RE = re.compile(
    "|".join([
        r"equal\s+(?:employment\s+)?opportunit",
        r"affirmative\s+action",
        r"without\s+regard\s+to",
        r"protected\s+(?:veteran|characteristic|class|status)",
        r"veteran\s+status",
        r"reasonable\s+accommodation",
        r"drug\s+(?:screen|test)",
        r"background\s+check",
        r"e-?verify",
        r"legally\s+authorized\s+to\s+work",
        r"authorized\s+to\s+work\s+in\s+the",
        r"reserves?\s+the\s+right\s+to",
        r"vested\s+right",
        r"contract\s+of\s+employment",
        r"posting\s+is\s+expected\s+to\s+(?:remain\s+open|close)",
        r"posting\s+will\s+remain\s+open",
        r"posted\s+until\s+filled",
        r"must\s+submit\s+an\s+online\s+application",
        r"sponsors?\s+certain\s+employee\s+benefit",
        r"pre-?employment\s+(?:screening|testing|drug)",
        r"employment\s+decisions\s+are\s+made",
        r"u\.?s\.?\s+based\s+position",
        r"applicants?\s+(?:must|will)\s+be\s+subject",
        r"it\s+is\s+our\s+policy\s+to\s+provide\s+equal",
        r"legally\s+protected",
    ]),
    re.IGNORECASE,
)

# Corporate mission / values / marketing prose → company.
_COMPANY_RE = re.compile(
    "|".join([
        r"\bour\s+(?:mission|values|culture|name|story|history|legacy|purpose)\b",
        r"\bmission\s+is\b",
        r"core\s+values",
        r"climate\s+crisis",
        r"decarboniz",
        r"sustainab",
        r"electrify\s+the\s+world",
        r"energy\s+to\s+change\s+the\s+world",
        r"lower\s+carbon|carbon\s+energy|clean\s+energy",
        r"reshape\s+industries",
        r"enrich\s+lives",
        r"transform\s+cities",
        r"life\s+is\s+on",
        r"impact\s+(?:values|maker)",
        r"trust\s+charter",
        r"code\s+of\s+conduct",
        r"ethics\s+and\s+compliance",
        r"learn\s+more\s+at",
        r"www\.",
        r"employees\s+(?:thrive|worldwide)",
        r"\d+\+?\s+countries",
        r"global\s+revenue",
        r"organic\s+growth",
        r"(?:€|\$|£)\s?\d+\s*billion",
        r"proud\s+to\s+(?:be|offer)",
        r"decades\s+of",
        r"growth\s+opportunit",
        r"we\s+(?:believe|celebrate|aspire|mirror)",
        r"great\s+work\s+environment",
        r"challenging\s+careers",
        r"competitive\s+compensation",
        r"apply\s+today",
        r"let\s+us\s+learn\s+about\s+you",
        r"\binclusiv",
        r"caring\s+company",
        r"culture\s+matters",
        r"join\s+(?:us|our\s+team)",
        r"treasured\s+legacy",
        r"badge\s+of\s+quality",
        r"connected\s+technologies",
    ]),
    re.IGNORECASE,
)

# Shift / hours / days prose → schedule.
_SCHEDULE_RE = re.compile(
    "|".join([
        r"\bshifts?\b",
        r"work\s+schedule",
        r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b",
        r"\bovertime\b",
        r"\bweekends?\b",
        r"full[-\s]?time|part[-\s]?time",
        r"hours?\s+per\s+week",
        r"\bonsite\s+position\b",
    ]),
    re.IGNORECASE,
)

# Pay-bearing sentence (a pay word near a dollar figure, or a $/hr amount).
_PAY_RE = re.compile(
    r"(?:\bpay(?:\s*rate)?\b|\bpayrate\b|\bstarting\s+rate\b|\bbase\s+rate\b|\bwage\b|"
    r"\bsalary\b|\bcompensation\b|\bpays\b|\bpaid\b)[^.]{0,80}?\d"
    r"|\$\s?\d[\d.,]*\s*(?:per\s+hour|/\s*hour|/\s*hr|an\s+hour|hourly|per\s+year|annually)",
    re.IGNORECASE,
)

# Bare restatement of the structured pay fact — captured into facts.pay_text
# and removed from prose (this is the sanctioned dedupe of a structured fact).
_PAY_BARE_RE = re.compile(
    r"^\*?\s*(?:the\s+)?pay(?:\s*rate)?\s+for\s+this\s+position\s+is\s+"
    r"\$?\s*[\d.,]+\s*(?:per\s+hour|per\s+year|hourly|annually|/\s*hour|/\s*hr)?\s*\.?$",
    re.IGNORECASE,
)

# Applicant-encouragement prose ("we still encourage you to apply") — role
# relevant, belongs in About the role rather than requirements or marketing.
_ENCOURAGE_RE = re.compile(
    r"we\s+know\s+skills|encourage\s+you\s+to\s+apply|"
    r"do\s+not\s+necessarily\s+meet\s+all",
    re.IGNORECASE,
)

# Role-referential language — breaks company/notice momentum back to "about".
_ROLE_RE = re.compile(
    r"\b(?:position|role|job|opportunity\s+for|you\s+will|you'll|your\b|responsib|"
    r"candidate|applicant|perform)\b",
    re.IGNORECASE,
)

# Marketing-flavored question headers ("How will you power what's possible?").
_MARKETING_QUESTION_RE = re.compile(
    r"^[A-Z][^?]{0,80}\b(?:career|impact|join|power|possible|ready|passion|team|culture)\b[^?]{0,40}\?$",
    re.IGNORECASE,
)

# Scraper UI chrome — apply-widget artifacts, not job content.
_JUNK_LINES = frozenset({"conversational apply", "standard apply", "apply now", "apply"})

# Inline CTA phrases used to split marketing tails off list items.
_CTA_SPLIT_RE = re.compile(r"\s+(?=(?:Let\s+us\s+learn\s+about\s+you|Join\s+us\s+today)\b)")

_MAX_HEADER_LEN = 60
_MAX_HEADER_WORDS = 8

# Words that legitimately dangle at the end of a wrapped line — the next line
# continues the sentence regardless of its capitalization.
_DANGLING_WORDS = frozenset(
    "a an the and or of to for with in on at is are be will their its our your as by "
    "from that this but not any each per plus such into upon than may must can have "
    "has had including include includes we you it they was were".split()
)

# Short lowercase fragments that are real words (join with a space) versus
# broken-off suffixes like "s" (concatenate without a space).
_SHORT_REAL_WORDS = frozenset(
    "a an as at be by do go he if in is it me my no of on or so to up us we and are "
    "but can for had has her him his how its may not now off one our out per she the "
    "too two was who why you all any few new old".split()
)

_PUNCT_START = re.compile(r"^[,.;:)%'’\]…]")
_BARE_NUMBER = re.compile(r"^[$€£]?\d[\d.,]*%?$")
# "- $28.40" continuing "…is $27.14" — a snapped pay-range dash.
_RANGE_DASH_START = re.compile(r"^[-–—]\s*[$€£\d]")

_SENTENCE_SPLIT = re.compile(
    # Sentence boundary, or the start of an application-process notice that the
    # source glued onto marketing stats without punctuation.
    r"(?<=[.!?…])\s+(?=[A-Z“\"'(€$\d])|\s+(?=You\s+must\s+submit\s+an\s+online\b)"
)

# A short heading-like phrase with a trailing colon glued to the end of an item
# ("… equivalency Classes in:") — split it off so it can act as a header.
_TRAILING_COLON_HEADER = re.compile(r"\s+(?=[A-Z][^:.!?]{2,50}:$)")


def _split_trailing_colon_header(item: str) -> list[str]:
    """Split a short heading-like colon phrase off the END of an item — at most
    once, and never when the item itself IS a header ("Rate of Pay and
    Benefits:" must stay whole)."""
    hm = _match_header(item)
    if hm is not None and hm[1] is None:
        return [item]  # the whole item is a pure header
    matches = list(_TRAILING_COLON_HEADER.finditer(item))
    if not matches:
        return [item]
    pos = matches[-1].end()
    head, label = item[:pos].strip(), item[pos:].strip()
    if len(head.split()) >= 4 and 1 <= len(label.split()) <= 8:
        return [head, label]
    return [item]

# Sub-bullet runs using " o " separators ("… o Technical/Shop Math o Basic …").
_O_RUN = re.compile(r"\s+o\s+(?=[A-Z])")

_STOPWORDS = frozenset(
    "a an the and or of to for with in on at is are be will was were been being has "
    "have had do does did this that these those it its as by from we you your our their "
    "they he she not no but if than then so such per each all any more most other some".split()
)

# Bump when parser behavior changes — folded into the content hash so cached
# rows parsed by an older version are recomputed on next read.
_PARSER_VERSION = "3"


def compute_content_hash(
    description_raw: str | None,
    requirements_raw: str | None,
    preferred_qualifications_raw: str | None,
    responsibilities_raw: str | None,
) -> str:
    """Stable sha256 over the raw inputs + parser version — cache key for
    parsed sections. Same inputs, same hash; re-scrape or parser upgrade
    changes it."""
    payload = "\x1e".join(
        (_PARSER_VERSION, description_raw or "", requirements_raw or "",
         preferred_qualifications_raw or "", responsibilities_raw or "")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Stage 1 — line repair (rejoin mid-word / mid-sentence snaps)
# ---------------------------------------------------------------------------

def _match_header(line: str) -> tuple[str, str | None] | None:
    """If `line` is a section header (optionally with inline content after a
    colon, or a leading question), return (bucket, remainder-or-None)."""
    stripped = line.strip()
    candidates: list[tuple[str, str | None]] = []
    # "HEADER: inline content" — the separator is a colon or a SPACED dash;
    # a bare hyphen would falsely split "Safety-conscious, quality-driven…".
    m = re.match(r"^([^:—]{2,60})\s*(?::|—|–|\s-\s)\s*(.*)$", stripped)
    if m:
        candidates.append((m.group(1).strip(), m.group(2).strip() or None))
    # "Question-form heading? inline content"
    qm = re.match(r"^([A-Z][^?]{2,80}\?)\s*(.*)$", stripped)
    if qm:
        candidates.append((qm.group(1).rstrip("? ").strip(), qm.group(2).strip() or None))
    # "Header (parenthetical qualifier)" — e.g. Delta's
    # "What you need to succeed (minimum qualifications)".
    pm = re.match(r"^(.{2,60})\s*\([^)]{2,60}\)$", stripped)
    if pm:
        candidates.append((pm.group(1).strip(), None))
    candidates.append((stripped.rstrip("?:-—– ").strip(), None))
    for head, rest in candidates:
        if len(head) > _MAX_HEADER_LEN:
            continue
        for pattern, bucket in _HEADER_BUCKETS:
            if pattern.match(head):
                return bucket, rest
    # Marketing question headings route their following content to company.
    if qm and _MARKETING_QUESTION_RE.match(qm.group(1)):
        return "company", (qm.group(2).strip() or None)
    if _MARKETING_QUESTION_RE.match(stripped):
        return "company", None
    return None


def _joins_previous(prev: str, cur: str) -> bool:
    """True when `cur` is a continuation fragment of `prev` (a snapped line)."""
    if not prev or not cur:
        return False
    if _PUNCT_START.match(cur):
        return True
    if prev.endswith(":"):
        # "Relocation Assistance Provided:" + "Yes" — or an unknown label with
        # a lowercase continuation ("Perform UT on:" + "rotors, casings…") —
        # but never swallow list content that follows a known section header.
        if _match_header(prev) is not None:
            return False
        return (len(cur.split()) <= 3 and not cur.endswith(":")) or cur[:1].islower()
    if _BARE_NUMBER.match(cur) or _RANGE_DASH_START.match(cur):
        return True
    if prev[-1] in "$€£/(-–—,;&":
        return True
    # A standalone dangling word ("…is an") means the sentence continues; the
    # anchor requires a whole word so "6:50p-7a" doesn't count as ending in "a".
    m = re.search(r"(?:^|\s)([A-Za-z']+)$", prev)
    if m and m.group(1).lower() in _DANGLING_WORDS:
        return True
    if cur[:1].islower():
        return True
    return False


def _join(prev: str, cur: str) -> str:
    """Join a continuation fragment, repairing mid-word snaps ("year" + "s")."""
    if _PUNCT_START.match(cur):
        return prev + cur
    if prev[-1] in "$€£/(-–—":
        return prev + cur
    first = cur.split()[0] if cur.split() else cur
    if (
        first.islower()
        and len(first) <= 3
        and first == cur.strip()  # the whole line is the fragment
        and first not in _SHORT_REAL_WORDS
        and prev[-1].isalpha()
    ):
        return prev + cur
    return f"{prev} {cur}"


def _repair_lines(raw: str) -> list[str]:
    """Split raw text into lines, strip bullet decoration, and re-join lines
    that were snapped mid-word or mid-sentence by the scraper."""
    out: list[str] = []
    for ln in raw.split("\n"):
        ln = _BULLET_PREFIX.sub("", ln.strip()).strip()
        ln = ln.lstrip("*").strip() if ln.startswith("*") else ln
        if not ln:
            continue
        if out and _joins_previous(out[-1], ln):
            out[-1] = _join(out[-1], ln)
        else:
            out.append(ln)
    return out


# ---------------------------------------------------------------------------
# Stage 2 — inline explosion (separator runs, embedded headings)
# ---------------------------------------------------------------------------

_QUESTION_HEAD_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-Z][^.?!]{0,80}\?)")
_DOT_SEP_SPLIT = re.compile(r"\s+[·•▪]\s+")


def _explode_megaline(line: str) -> list[str]:
    """Break one huge newline-free blob into item-sized pieces using
    double-space separators and inline ALL-CAPS header boundaries."""
    if len(line) < _MEGALINE_MIN:
        return [line]
    pieces: list[str] = []
    for seg in _MULTISPACE_SPLIT.split(line):
        for piece in _INLINE_CAPS_HEADER_SPLIT.split(seg):
            piece = piece.strip()
            if piece:
                pieces.append(piece)
    return pieces or [line]


def _explode_inline(line: str) -> list[str]:
    """Split a repaired line into item-sized pieces: question-form headings,
    inline "·" separator runs, " o " sub-bullet runs, mega-line blobs, glued
    CTA tails, and trailing heading-like colon phrases."""
    results: list[str] = []
    for qpiece in _QUESTION_HEAD_SPLIT.split(line):
        for piece in _DOT_SEP_SPLIT.split(qpiece):
            piece = piece.strip()
            if not piece:
                continue
            for mpiece in _explode_megaline(piece):
                mpiece = _BULLET_PREFIX.sub("", mpiece.strip()).strip()
                if not mpiece:
                    continue
                if len(_O_RUN.findall(mpiece)) >= 2:
                    subitems = [s.strip() for s in _O_RUN.split(mpiece) if s.strip()]
                else:
                    subitems = [mpiece]
                for sub in subitems:
                    for cta_part in _CTA_SPLIT_RE.split(sub):
                        for final in _split_trailing_colon_header(cta_part.strip()):
                            final = final.strip()
                            if final:
                                results.append(final)
    return results


def _clean_lines(raw: str) -> list[str]:
    lines: list[str] = []
    for repaired in _repair_lines(raw):
        lines.extend(_explode_inline(repaired))
    return lines


# ---------------------------------------------------------------------------
# Stage 3 — classification
# ---------------------------------------------------------------------------

def _is_prose(line: str) -> bool:
    """Long multi-clause text reads as a paragraph, not a bullet."""
    return len(line) > 200 or (len(line) > 120 and ". " in line)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _looks_like_header_label(line: str) -> bool:
    """Header-shaped but unmatched: short ALL-CAPS labels or short colon lines."""
    if len(line) > _MAX_HEADER_LEN + 20 or len(line.split()) > _MAX_HEADER_WORDS:
        return False
    if re.match(r"^[A-Z][A-Z\s/&-]{2,40}(?::|\()", line):
        return True
    if line.endswith(":") and len(line.split()) <= _MAX_HEADER_WORDS:
        return True
    return False


def _infer_header_bucket(label: str) -> str | None:
    for pattern, bucket in _HEADER_KEYWORD_BUCKETS:
        if pattern.search(label):
            return bucket
    return None


def _content_tokens(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9']+", text.lower())
        if t not in _STOPWORDS and len(t) > 1
    }


def _split_long_paragraph(text: str, max_words: int = 90) -> list[str]:
    """Break a wall of text into readable paragraphs at sentence boundaries."""
    words = text.split()
    if len(words) <= max_words:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    count = 0
    for sentence in _split_sentences(text):
        n = len(sentence.split())
        if current and count + n > max_words * 0.75:
            chunks.append(" ".join(current))
            current, count = [], 0
        current.append(sentence)
        count += n
    if current:
        chunks.append(" ".join(current))
    return chunks or [text]


def parse_job_sections(
    description_raw: str | None,
    requirements_raw: str | None = None,
    preferred_qualifications_raw: str | None = None,
    responsibilities_raw: str | None = None,
) -> dict:
    """Deterministically reorganize raw scraped job text into the display schema."""
    sections: dict[str, list[str]] = {k: [] for k in SECTION_KEYS}
    facts: dict[str, str | None] = {"shift": None, "pay_text": None, "location_text": None}
    unclassified = 0
    seen: set[str] = set()
    bucket_tokens: dict[str, set[str]] = {k: set() for k in SECTION_KEYS}

    def _add(bucket: str, text: str) -> None:
        text = text.strip()
        # Presentation standardization only: bullets start with a capital.
        # (Some sources author list items lowercase; this changes case, never
        # words.) Repair logic has already rejoined true snapped fragments.
        if text[:1].islower():
            text = text[0].upper() + text[1:]
        key = re.sub(r"\W+", " ", text).strip().lower()
        if not key or key in seen:
            return
        # Near-duplicate suppression within a bucket (re-worded repeats of the
        # same benefits paragraph / differential line are noise, not content).
        tokens = _content_tokens(text)
        if tokens and len(tokens) >= 6:
            overlap = len(tokens & bucket_tokens[bucket]) / len(tokens)
            if overlap >= 0.8:
                return
        seen.add(key)
        bucket_tokens[bucket] |= tokens
        sections[bucket].append(text)

    def _capture_pay(sentence: str) -> None:
        if facts["pay_text"] is None:
            facts["pay_text"] = sentence.strip().rstrip(".").strip()

    def _walk_sentences(text: str, seed: str, momentum: str | None) -> str | None:
        """Classify prose sentence-by-sentence; group contiguous same-class
        sentences into paragraphs. Returns the ending momentum class."""
        groups: list[tuple[str, list[str]]] = []
        last: str | None = momentum
        for s in _split_sentences(text):
            hm = _match_header(s)
            if hm is not None and hm[1] is None:
                continue  # a header label glued into prose is structure, not content
            if _NOTICE_RE.search(s):
                b = "notices"
            elif _PAY_RE.search(s):
                _capture_pay(s)
                if _PAY_BARE_RE.match(s):
                    # Bare restatement of the structured pay fact — the amount
                    # survives in facts.pay_text; drop the fragment from prose.
                    last = "benefits"
                    continue
                b = "benefits"
            elif _ENCOURAGE_RE.search(s):
                b = "about"
            elif _COMPANY_RE.search(s):
                b = "company"
            elif _SCHEDULE_RE.search(s):
                b = "schedule"
            elif _BENEFIT_LINE.search(s):
                b = "benefits"
            elif _ROLE_RE.search(s):
                b = seed if seed in _STICKY_BUCKETS else "about"
            elif last in ("company", "notices", "benefits", "schedule"):
                b = last
            else:
                b = seed if seed in _STICKY_BUCKETS else "about"
            # Benefits render as bullets — one sentence per item; prose buckets
            # group contiguous same-class sentences into paragraphs.
            if groups and groups[-1][0] == b and b != "benefits":
                groups[-1][1].append(s)
            else:
                groups.append((b, [s]))
            last = b
        for b, sents in groups:
            _add(b, " ".join(sents))
        return last

    def _consume(raw: str | None, default_bucket: str) -> None:
        """Walk lines, tracking the current header context. `default_bucket` is
        where otherwise-unclassifiable content lands."""
        nonlocal unclassified
        if not raw or not raw.strip():
            return
        current: str = default_bucket
        momentum: str | None = None
        for line in _clean_lines(raw):
            if line.lower().strip(".!") in _JUNK_LINES:
                continue  # scraper apply-widget chrome, not job content

            # Fact lines duplicate structured data — capture and drop.
            fact_hit = False
            for fact_key, pattern in _FACT_PATTERNS.items():
                fm = pattern.match(line)
                if fm and len(line) < 80:
                    if facts[fact_key] is None:
                        facts[fact_key] = fm.group(1).strip()
                    fact_hit = True
                    break
            if fact_hit:
                continue

            header = _match_header(line)
            if header is not None:
                current, remainder = header
                momentum = None
                if remainder:
                    if _is_prose(remainder):
                        momentum = _walk_sentences(remainder, current, None)
                    else:
                        _add(current, remainder)
                continue

            # Unknown header-shaped labels: route by keyword, else keep context.
            if _looks_like_header_label(line):
                inferred = _infer_header_bucket(line)
                if inferred is not None:
                    current = inferred
                momentum = None
                continue

            if _is_prose(line):
                momentum = _walk_sentences(line, current, momentum)
                continue

            # Bullet-sized line: strong cues first, then header context.
            if _NOTICE_RE.search(line):
                _add("notices", line)
                momentum = "notices"
            elif _PAY_RE.search(line):
                _capture_pay(line)
                if not _PAY_BARE_RE.match(line):
                    _add("benefits", line)
                momentum = None
            elif _COMPANY_RE.search(line):
                _add("company", line)
                momentum = "company"
            elif _BENEFIT_LINE.search(line):
                _add("benefits", line)
                momentum = None
            elif current in _STICKY_BUCKETS:
                _add(current, line)
            elif _NEEDS_LINE.match(line):
                _add("needs", line)
            elif _DUTY_LINE.match(line):
                _add("duties", line)
            elif momentum in ("company", "notices") and not _ROLE_RE.search(line):
                # Continuation of a marketing / legal block ("If we want our
                # energy future to be different…we must be different.").
                _add(momentum, line)
            else:
                # Short line that fits nowhere — keep it visible in "about" but
                # count it: too many of these means the parse is unreliable.
                unclassified += 1
                _add("about", line)

    _consume(description_raw, "about")
    _consume(responsibilities_raw, "duties")
    _consume(requirements_raw, "needs")
    _consume(preferred_qualifications_raw, "nice_to_have")

    # Walls of text must never appear: split long paragraphs for readability.
    for key in ("about", "company", "notices", "benefits"):
        split_items: list[str] = []
        for item in sections[key]:
            split_items.extend(_split_long_paragraph(item))
        sections[key] = split_items

    raw_len = sum(
        len(x or "")
        for x in (description_raw, requirements_raw,
                  preferred_qualifications_raw, responsibilities_raw)
    )
    list_items = sum(
        len(sections[k]) for k in ("duties", "needs", "nice_to_have", "benefits")
    )
    # Messy = unreliable parse: many unclassifiable fragments, or long raw text
    # that produced no lists, or a giant undigested wall of text in "about".
    huge_about = any(len(p) > 600 for p in sections["about"])
    messy = unclassified >= 4 or (raw_len > 800 and (list_items == 0 or huge_about))

    return {
        **sections,
        "facts": facts,
        "quality": "messy" if messy else "good",
    }


# ---------------------------------------------------------------------------
# LLM fallback — reorganize only, never invent. Sync (call via asyncio.to_thread).
# Post-validated to be extractive; deterministic result is the floor.
# ---------------------------------------------------------------------------

_LLM_SYSTEM = (
    "You reorganize scraped job-posting text into a fixed JSON schema. "
    "EXTRACTIVE ONLY: every output sentence must be copied or minimally trimmed "
    "from the provided text — never add, invent, reword, or embellish facts, "
    "numbers, or requirements. Merge broken line wraps. Return JSON with exactly "
    "these keys: about (role-relevant prose paragraphs, list of strings), "
    "duties (responsibility bullets), needs (required qualification bullets), "
    "nice_to_have (preferred qualification bullets), benefits (pay context and "
    "benefit bullets), schedule (shift/hours lines), company (mission, values, "
    "and marketing prose), notices (EEO statements, drug/background screening, "
    "legal disclaimers, benefit-plan sponsor legalese), facts (object with "
    "shift, pay_text, location_text — string or null, copied verbatim from the "
    "text). Every piece of source content must land in exactly one section; "
    "use empty lists for absent sections."
)


def _extractive_ok(item: str, source_tokens: set[str]) -> bool:
    """Deterministic no-hallucination check: an output item passes only when
    nearly all of its content words appear in the source text."""
    tokens = _content_tokens(item)
    if not tokens:
        return True
    return len(tokens & source_tokens) / len(tokens) >= 0.85


def _validate_llm_sections(data: dict, source_text: str, fallback: dict) -> dict | None:
    """Coerce + validate an LLM response. Returns a clean sections dict, or
    None when too much content failed the extractive check."""
    source_tokens = _content_tokens(source_text)
    out: dict = {}
    total = 0
    dropped = 0
    for key in SECTION_KEYS:
        val = data.get(key)
        items = [str(v).strip() for v in val if str(v).strip()] if isinstance(val, list) else []
        kept: list[str] = []
        for item in items:
            total += 1
            if _extractive_ok(item, source_tokens):
                kept.append(item)
            else:
                dropped += 1
        out[key] = kept
    if total == 0 or not any(out[k] for k in SECTION_KEYS):
        return None
    if dropped / total > 0.2:
        return None  # model rewrote too much — untrustworthy output
    raw_facts = data.get("facts") if isinstance(data.get("facts"), dict) else {}
    out["facts"] = {}
    for k in ("shift", "pay_text", "location_text"):
        v = str(raw_facts[k]).strip() if raw_facts.get(k) else None
        if v and not _extractive_ok(v, source_tokens):
            v = None
        out["facts"][k] = v or fallback["facts"].get(k)
    out["quality"] = "good"
    return out


def llm_reorganize_sections(
    description_raw: str | None,
    requirements_raw: str | None = None,
    preferred_qualifications_raw: str | None = None,
    responsibilities_raw: str | None = None,
    deterministic_result: dict | None = None,
) -> dict:
    """One bounded LLM call to reorganize messy text, post-validated to be
    extractive (one corrective retry). Returns the deterministic result
    unchanged on any failure or missing API key."""
    fallback = deterministic_result or parse_job_sections(
        description_raw, requirements_raw, preferred_qualifications_raw, responsibilities_raw
    )
    from app.config import get_settings
    from app.util.openai_client import get_openai_client

    client = get_openai_client()
    if client is None:
        return fallback

    parts = []
    if description_raw:
        parts.append(f"DESCRIPTION:\n{description_raw}")
    if responsibilities_raw:
        parts.append(f"RESPONSIBILITIES:\n{responsibilities_raw}")
    if requirements_raw:
        parts.append(f"REQUIREMENTS:\n{requirements_raw}")
    if preferred_qualifications_raw:
        parts.append(f"PREFERRED QUALIFICATIONS:\n{preferred_qualifications_raw}")
    if not parts:
        return fallback
    source_text = "\n\n".join(parts)[:20000]

    messages = [
        {"role": "system", "content": _LLM_SYSTEM},
        {"role": "user", "content": source_text},
    ]
    try:
        for attempt in range(2):
            resp = client.chat.completions.create(
                model=get_settings().llm_extraction_model or "gpt-4o-mini",
                temperature=0,
                response_format={"type": "json_object"},
                messages=messages,
            )
            content = resp.choices[0].message.content or "{}"
            validated = _validate_llm_sections(json.loads(content), source_text, fallback)
            if validated is not None:
                return validated
            if attempt == 0:
                # One corrective regeneration: repeat with an explicit reminder.
                messages = messages + [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            "Some of your output was not copied from the source text. "
                            "Regenerate the JSON using ONLY verbatim or minimally "
                            "trimmed sentences from the source."
                        ),
                    },
                ]
        logger.warning("job_sections LLM output failed extractive validation twice; using parser result")
        return fallback
    except Exception as exc:  # noqa: BLE001 — any LLM failure degrades gracefully
        logger.warning("job_sections LLM fallback failed, using parser result: %s", exc)
        return fallback
