"""
Guardrails for the applicant planning chat.

The chat advises real trainees — often young, sometimes discouraged — about
their careers. A raw LLM can (a) be manipulated into harmful output, (b)
fabricate jobs/pay/promises we never made, or (c) crush someone's motivation.
This module wraps every exchange in a standard three-stage pipeline:

  1. INPUT moderation   — OpenAI moderation endpoint (omni-moderation-latest);
                          flagged input gets a calm refusal, and self-harm
                          signals get a supportive message with the 988 line.
  2. GROUNDED PROMPT    — the system prompt pins the model to the stored match
                          context and bans promises/guarantees, legal/medical/
                          financial advice, and discouraging language.
  3. OUTPUT validation  — deterministic checks on the reply:
                            • harmful content (moderation again),
                            • fabricated agency ("I've scheduled/applied…"),
                            • guarantee/promise claims,
                            • discouraging phrasing,
                            • employers named that aren't in the context.
                          One corrective regeneration is attempted; if the
                          retry still fails checks, a safe deterministic
                          fallback built from the match data is used instead.

Every tripped guardrail is queued to `review_queue_items` (item_type
'chat_guardrail') so admins can audit what the model tried to say, and the
stored message carries `guardrail_meta` for observability.

Design notes:
- All validation here is DETERMINISTIC (regex/pattern + set membership), so the
  guard layer itself cannot hallucinate. LLM-based self-critique was rejected:
  it doubles latency and cost and is itself un-auditable.
- Moderation uses the shared resilient client budget (fast connect timeout);
  if the moderation API is down we fail SAFE for output (fallback text) and
  fail OPEN for input (the output check still protects us).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GUARDRAIL_VERSION = "v1"

# ---------------------------------------------------------------------------
# System prompt (grounded, tone-guarded). Replaces the looser prompt in
# services/chat.py — chat.py imports this constant.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a career planning advisor for SKILLED Nation, a skilled-trades workforce platform run by the nonprofit that funds the applicant's training.
You are talking with a trainee (they may be young or early-career). Your job is to help them act on their job matches.

GROUNDING RULES — the most important rules:
- Base every factual claim about jobs, employers, scores, strengths, and gaps ONLY on the [Current applicant context] block. It is the single source of truth.
- Never invent job listings, employers, pay numbers, requirements, dates, or contact details that are not in the context.
- If you don't know or the context doesn't say, say exactly that — "I don't have that information" — and point to what they can do to find out.
- Never state or estimate specific pay unless a pay figure appears in the context.

TONE RULES:
- Be encouraging AND honest. Name gaps plainly, then immediately give the concrete next step to close them.
- Never be discouraging: no "you can't", "you'll never", "not qualified", "give up", or any framing that the situation is hopeless. Every gap gets a path.
- Keep responses short: 3–5 sentences, or a short list when steps are involved.

SCOPE RULES:
- You do not take actions. Never claim to have applied, scheduled, contacted an employer, or changed anything on the applicant's behalf.
- Never promise or predict hiring outcomes ("you'll definitely get this job"). Say what improves their chances instead.
- No legal, medical, immigration, or financial advice — suggest they speak to a qualified professional for those.
- If asked something unrelated to careers, training, or their job search, politely steer back to career planning.

SAFETY:
- If the applicant expresses intent to harm themselves or others, respond with care, do not lecture, and share that the 988 Suicide & Crisis Lifeline (call or text 988) is available 24/7 — then gently continue supporting them.
"""

# ---------------------------------------------------------------------------
# Deterministic output checks
# ---------------------------------------------------------------------------

# The assistant claiming to have DONE something (it has no ability to act).
_AGENCY_PATTERNS = [
    r"\bI(?:'ve| have)\s+(?:applied|scheduled|submitted|contacted|emailed|arranged|booked)\b",
    r"\bI\s+(?:applied|scheduled|submitted|contacted|emailed|arranged|booked)\s",
    r"\byour (?:interview|application) (?:has been|is) (?:scheduled|submitted)\b",
]

# Outcome guarantees we must never make.
_GUARANTEE_PATTERNS = [
    r"\bguaranteed?\b.{0,40}\b(?:job|hire|offer|position|interview)\b",
    r"\b(?:job|hire|offer|position|interview)\b.{0,40}\bguaranteed?\b",
    r"\byou (?:will|'ll) (?:definitely|certainly|surely) (?:get|be hired|receive an offer)\b",
    r"\bI (?:promise|assure you)\b",
]

# Motivation-crushing phrasing. The prompt bans it; this catches leaks.
_DISCOURAGING_PATTERNS = [
    r"\byou(?:'re| are) not (?:qualified|good enough|cut out)\b",
    r"\byou(?:'ll| will) never\b",
    r"\b(?:give up|no chance|hopeless|pointless|waste of time)\b",
    r"\bdon'?t bother\b",
    r"\bnot worth (?:applying|trying)\b",
]

# Words that negate a "guarantee" phrase — "no certification can guarantee an
# interview" is honest advice, not a promise. Checked in the 24 chars before a
# guarantee-pattern hit.
_NEGATION_BEFORE = re.compile(
    r"\b(?:no|not|never|can'?t|cannot|won'?t|doesn'?t|nothing)\b[^.!?]{0,24}$",
    re.IGNORECASE,
)

_CHECKS = {
    "agency_claim": _AGENCY_PATTERNS,
    "outcome_guarantee": _GUARANTEE_PATTERNS,
    "discouraging_tone": _DISCOURAGING_PATTERNS,
}


@dataclass
class GuardrailResult:
    """Outcome of the output-validation stage for one reply."""
    ok: bool
    checks_failed: list[str] = field(default_factory=list)
    # 'passed' | 'regenerated' | 'fallback' | 'refused'
    action: str = "passed"

    def meta(self) -> dict[str, Any]:
        return {
            "version": GUARDRAIL_VERSION,
            "checks_failed": self.checks_failed,
            "action": self.action,
        }


def _known_employers(context_snapshot: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for m in context_snapshot.get("top_matches", []) or []:
        if m.get("employer"):
            names.add(str(m["employer"]).lower())
    fj = context_snapshot.get("focused_job") or {}
    if fj.get("employer"):
        names.add(str(fj["employer"]).lower())
    return names


def validate_reply(reply: str, context_snapshot: dict[str, Any]) -> list[str]:
    """Run deterministic content checks. Returns the list of failed check names."""
    failed: list[str] = []
    for name, patterns in _CHECKS.items():
        for pat in patterns:
            m = re.search(pat, reply, re.IGNORECASE)
            if not m:
                continue
            # Guarantee phrases preceded by a negation ("no cert can guarantee…")
            # are honest advice — skip them.
            if name == "outcome_guarantee" and _NEGATION_BEFORE.search(reply[: m.start()]):
                continue
            failed.append(name)
            break

    # Fabricated-employer check: "at <Proper Name>" phrases naming an employer
    # that isn't in the grounded context. Conservative on purpose — only exact
    # "at X"/"with X" attachments, title-cased, len>3, not in context and not a
    # common non-employer phrase — so real advice never trips it.
    known = _known_employers(context_snapshot)
    if known:  # only enforceable when we have context to check against
        for m in re.finditer(r"\b(?:at|with)\s+([A-Z][A-Za-z&']+(?:\s+[A-Z][A-Za-z&']+){0,3})", reply):
            candidate = m.group(1).strip()
            if len(candidate) <= 3:
                continue
            cand_lower = candidate.lower()
            if any(cand_lower in k or k in cand_lower for k in known):
                continue
            if cand_lower in _NON_EMPLOYER_PHRASES:
                continue
            failed.append("unknown_employer_mention")
            break

    return failed


# Title-cased phrases that commonly follow "at/with" but are not employers.
_NON_EMPLOYER_PHRASES = {
    "skilled nation", "skilled", "skillpointe", "osha", "aws", "nccer", "epa",
    "hvac", "the", "first", "least", "most", "best", "this", "that", "your",
    "home", "work", "night", "school", "community college", "trade school",
}


# ---------------------------------------------------------------------------
# Moderation (OpenAI omni-moderation) — input and output
# ---------------------------------------------------------------------------

_SELF_HARM_CATEGORIES = {"self-harm", "self-harm/intent", "self-harm/instructions"}


async def moderate(text: str) -> tuple[bool, list[str]]:
    """Return (flagged, categories). Fails open (False, []) if unavailable —
    callers combine this with the deterministic checks, which always run."""
    from app.config import get_settings
    from app.util.openai_client import interactive_http_timeout

    settings = get_settings()
    if not settings.openai_api_key or len(text) > 20_000:
        return False, []
    try:
        async with httpx.AsyncClient(timeout=interactive_http_timeout()) as client:
            resp = await client.post(
                "https://api.openai.com/v1/moderations",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": "omni-moderation-latest", "input": text[:10_000]},
            )
        if resp.status_code != 200:
            return False, []
        result = (resp.json().get("results") or [{}])[0]
        if not result.get("flagged"):
            return False, []
        cats = [k for k, v in (result.get("categories") or {}).items() if v]
        return True, cats
    except Exception:  # moderation outage must never break chat
        logger.warning("Moderation call failed; continuing with deterministic checks only")
        return False, []


def self_harm_response() -> str:
    return (
        "I'm really glad you told me. You don't have to carry that alone. The 988 "
        "Suicide & Crisis Lifeline is there 24/7, just call or text 988 to talk with "
        "someone right now. Your training and your future matter, and I'm here to "
        "keep helping you plan whenever you're ready."
    )


def refusal_response() -> str:
    return (
        "I can't help with that, but I'm here for anything about your job matches, "
        "training, certifications, or next steps. What would you like to work on?"
    )


# ---------------------------------------------------------------------------
# Deterministic fallback — a USEFUL answer with zero LLM involvement
# ---------------------------------------------------------------------------

def deterministic_fallback(context_snapshot: dict[str, Any]) -> str:
    """Built only from stored match data, so it can never hallucinate. Used when
    the LLM is unavailable or a reply failed validation twice."""
    fj = context_snapshot.get("focused_job") or {}
    if fj:
        parts: list[str] = []
        title = fj.get("job_title") or "this role"
        employer = fj.get("employer")
        head = f"Here's where you stand on {title}" + (f" at {employer}" if employer else "") + ":"
        parts.append(head)
        if fj.get("top_strengths"):
            parts.append("Working for you: " + "; ".join(map(str, fj["top_strengths"][:3])) + ".")
        if fj.get("required_missing_items"):
            parts.append("Required items to close: " + "; ".join(map(str, fj["required_missing_items"][:3])) + ".")
        elif fj.get("top_gaps"):
            parts.append("Gaps to work on: " + "; ".join(map(str, fj["top_gaps"][:3])) + ".")
        if fj.get("recommended_next_step"):
            parts.append(f"Recommended next step: {fj['recommended_next_step']}")
        parts.append("Ask me about any of these and I'll break it down.")
        return "\n\n".join(parts)

    matches = context_snapshot.get("top_matches") or []
    if matches:
        top = matches[0]
        lines = ["Here's a quick snapshot from your matches:"]
        lines.append(
            f"Your strongest match is {top.get('job_title', 'a role')}"
            + (f" at {top.get('employer')}" if top.get("employer") else "")
            + (f" ({round(top['score'])}/100)." if isinstance(top.get("score"), (int, float)) else ".")
        )
        if top.get("top_gaps"):
            lines.append("Biggest gap to close: " + str(top["top_gaps"][0]) + ".")
        if top.get("recommended_next_step"):
            lines.append(f"Suggested next step: {top['recommended_next_step']}")
        return "\n".join(lines)

    return (
        "I can help you plan your next move, but I don't see match data yet. "
        "Finish your profile so we can rank real openings for you, then ask me "
        "anything about certifications, timing, or how to apply."
    )


# ---------------------------------------------------------------------------
# Suggested questions — rule-based scaffolding (deterministic, no LLM)
# ---------------------------------------------------------------------------

def suggested_questions(context_snapshot: dict[str, Any]) -> list[str]:
    """Contextual starter questions. Deterministic on purpose: suggestions are
    part of the UI chrome and must never hallucinate."""
    fj = context_snapshot.get("focused_job") or {}
    if fj:
        title = fj.get("job_title") or "this role"
        qs: list[str] = []
        if fj.get("required_missing_items"):
            first = str(fj["required_missing_items"][0])
            qs.append(f"How do I get the {first}?")
        elif fj.get("top_gaps"):
            qs.append("What should I tackle first to close my gaps?")
        qs.append(f"What certifications matter most for a {title}?")
        qs.append("How should I describe my training when I apply?")
        qs.append(f"What is a typical day like as a {title}?")
        qs.append("What should I expect from the hiring process?")
        return qs[:4]

    return [
        "Which of my matches should I focus on first?",
        "What one certification would improve my matches most?",
        "How do I make my profile stronger for employers?",
        "What should I do this week to move forward?",
    ]
