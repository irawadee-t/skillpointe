"""
explanation_voice.py — deterministic perspective transforms for match
explanations, plus grounding guards for AI-generated candidate reasons.

The engine writes top_strengths / top_gaps / recommended_next_step in the
APPLICANT's voice ("Your trade matches this role", "~18 mi from Troy,
inside your 50 mi radius", "You're a strong match. Apply now."). Employers
see the same stored rows, so anything served on an employer surface must be
re-voiced: same facts, employer perspective, no applicant-directed advice.

All transforms here are pure string functions (regex + exact maps) so they
are unit-testable and can never invent a fact that isn't in the input —
mirroring the deterministic-guardrail principle of chat_guardrails.py.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Employer voice — strengths / gaps
# ---------------------------------------------------------------------------

# Exact engine labels → employer-voice equivalents (same claim, third person).
_EXACT = {
    "Your trade matches this role": "Trade matches this role",
    "You have the credentials": "Has the required credentials",
    "Location works for you": "Location works",
    "Timing is right": "Timing works",
    "Available now": "Available now",
    "No extra credentials required": "Meets the posted requirements",
    # legacy wording (rows scored before the 2026-08 wording fix)
    "No extra credentials required for this job": "Meets the posted requirements",
    "Matches employer preferences": "Matches your posted preferences",
    "Different trade background": "Different trade background",
}

# Ordered regex rewrites for sentence-style rationales. Facts (distances,
# counts, credential names) pass through untouched; only the point of view
# and applicant-directed advice change.
_SUBS: list[tuple[re.Pattern[str], str]] = [
    # applicant-directed advice clauses — drop entirely
    (re.compile(r";?\s*consider widening your radius or updating relocation settings"), ""),
    (re.compile(r";?\s*consider relocation settings"), ""),
    (re.compile(r"\bset your commute radius or relocation preferences to confirm\b"),
     "commute preferences not set yet"),
    (re.compile(r"\bwiden your radius or update relocation settings if you'd travel\b",
                re.IGNORECASE),
     "outside their commute preferences"),
    (re.compile(r"\bplease update your profile\b"), "profile incomplete"),
    # radius phrasing: the radius belongs to the candidate
    (re.compile(r"\binside your (\d+) mi radius\b"), r"within their \1 mi commute radius"),
    (re.compile(r"\bjust beyond your (\d+) mi radius\b"), r"just beyond their \1 mi commute radius"),
    (re.compile(r"\bbeyond your (\d+) mi radius\b"), r"beyond their \1 mi commute radius"),
    (re.compile(r"\bbeyond the default (\d+) mi radius\b"), r"beyond their default \1 mi commute radius"),
    (re.compile(r"\bIn your city\b"), "In the job's city"),
    (re.compile(r"\bin your city\b"), "in the job's city"),
    (re.compile(r"\bFinishing your program\b"), "Finishing their program"),
    (re.compile(r"\byour program\b"), "their program"),
    (re.compile(r"\byour training is in\b"), "their training is in"),
    (re.compile(r"\byou have a\b"), "they have a"),
    (re.compile(r"\byou have\b"), "they have"),
    (re.compile(r"\byou're\b", re.IGNORECASE), "they're"),
    (re.compile(r"\bYour\b"), "Their"),
    (re.compile(r"\byour\b"), "their"),
    (re.compile(r"\byou\b"), "they"),
]


def to_employer_voice(text: str) -> str:
    """Re-voice one applicant-facing explanation sentence for an employer.

    Deterministic: exact-label map first, then perspective regexes. Numbers
    and names are never altered — only pronouns/advice."""
    if not text:
        return text
    mapped = _EXACT.get(text)
    if mapped is not None:
        return mapped
    out = text
    for pat, repl in _SUBS:
        out = pat.sub(repl, out)
    # tidy artifacts from dropped clauses
    out = re.sub(r"\s+—\s*$", "", out).strip().rstrip(";,— ").strip()
    return out


# Next-step sentences are actions — the applicant's action ("apply now") must
# become the employer's action ("consider reaching out"), not a re-pronouned
# version of the same advice.
_NEXT_STEP_EXACT = {
    "You're a strong match. Apply now.": "Strong match. Consider reaching out.",
    "Good fit. Review the description and apply.": "Good fit. Review their profile.",
    "Close match. Check the requirements.": "Close match. Review their profile.",
    "Different trade background. Keep building your skills.": "Different trade background",
    # legacy wording (rows scored before the 2026-08 em-dash copy fix)
    "You're a strong match — apply now": "Strong match. Consider reaching out.",
    "Good fit — review the description and apply": "Good fit. Review their profile.",
    "Close match — check the requirements": "Close match. Review their profile.",
    "Different trade background — keep building your skills": "Different trade background",
}


def next_step_for_employer(text: str | None) -> str | None:
    if not text:
        return text
    mapped = _NEXT_STEP_EXACT.get(text)
    if mapped is not None:
        return mapped
    if text.startswith("Look into: "):
        return "Gap to close: " + to_employer_voice(text[len("Look into: "):])
    if text.startswith("Outside your commute area"):
        return "Outside their commute area"
    if text.startswith("Worth a look: "):
        return "Worth a look: " + to_employer_voice(text[len("Worth a look: "):])
    # legacy wording (rows scored before the 2026-08 em-dash copy fix)
    if text.startswith("Worth a look — "):
        return "Worth a look: " + to_employer_voice(text[len("Worth a look — "):])
    return to_employer_voice(text)


# ---------------------------------------------------------------------------
# AI-priority reason guard (deterministic output validation)
# ---------------------------------------------------------------------------

_BANNED_REASON_PATTERNS = [
    re.compile(r"\bguarantee[ds]?\b", re.IGNORECASE),
    re.compile(r"\bdefinitely (?:will|get|be hired)\b", re.IGNORECASE),
    re.compile(r"\bpromise[sd]?\b", re.IGNORECASE),
    re.compile(r"\bbest candidate in the (?:country|state|world)\b", re.IGNORECASE),
]

_MAX_REASON_LEN = 220


def _digit_runs(text: str) -> set[str]:
    return set(re.findall(r"\d+", text))


def validate_priority_reason(reason: str, source_text: str) -> str | None:
    """Deterministically validate one LLM-written prioritization sentence.

    ``source_text`` is the exact grounded input the model was given for this
    candidate (name, score, status, strengths, gaps + job title). The reason
    is rejected (→ None, caller falls back to a deterministic sentence) when:
      - it is empty or implausibly long,
      - it contains any number that does not appear in the grounded input
        (an invented score, pay figure, distance, or years-of-experience),
      - it makes promise/guarantee claims the platform never makes.
    Mirrors the deterministic-validation bar of services/chat_guardrails.py.
    """
    if not reason or not reason.strip():
        return None
    cleaned = " ".join(reason.split())
    if len(cleaned) > _MAX_REASON_LEN:
        return None
    if not _digit_runs(cleaned) <= _digit_runs(source_text):
        return None
    for pat in _BANNED_REASON_PATTERNS:
        if pat.search(cleaned):
            return None
    return cleaned


def fallback_priority_reason(strengths: list[str]) -> str:
    """Honest deterministic reason when no validated LLM sentence exists.

    Prints the candidate's OWN top engine-computed strength (distance,
    availability, trade alignment, …) so a list of fallbacks differs per
    candidate. Returns "" when there is nothing candidate-specific to say —
    the UI then renders no reason line instead of repeating one boilerplate
    sentence for every row.
    """
    voiced = [to_employer_voice(s) for s in strengths if s]
    if voiced:
        first = voiced[0].strip().rstrip(".")
        if first:
            return f"{first[0].upper() + first[1:]}."
    return ""
