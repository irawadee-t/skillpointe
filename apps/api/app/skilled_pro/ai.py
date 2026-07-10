"""
AI profile-summary generation for workers.

Grounded: the prompt contains ONLY the worker's real, structured facts (trade,
location, verified credentials, availability) and instructs the model not to
invent anything. Degrades gracefully — if no OpenAI key is configured or the call
fails, a deterministic template summary is returned, so the feature always works
and never blocks. Pure prompt-building + fallback are unit-tested.
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You write concise, professional career summaries for U.S. skilled-trades "
    "workers. Write 2-3 sentences in third person, confident but factual. Use ONLY "
    "the facts provided — never invent credentials, employers, years of experience, "
    "or skills. No headers, no markdown, no first person."
)


def _facts_block(profile: dict[str, Any]) -> str:
    lines: list[str] = []
    if profile.get("name"):
        lines.append(f"Name: {profile['name']}")
    if profile.get("trade"):
        lines.append(f"Trade / program: {profile['trade']}")
    elif profile.get("program"):
        lines.append(f"Program: {profile['program']}")
    loc = ", ".join(p for p in [profile.get("city"), profile.get("state")] if p)
    if loc:
        lines.append(f"Location: {loc}")
    if profile.get("available_from"):
        lines.append(f"Available from: {profile['available_from']}")
    if profile.get("willing_to_relocate"):
        lines.append("Open to relocation: yes")
    creds = profile.get("credentials") or []
    if creds:
        rendered = "; ".join(
            f"{c['name']}" + (f" ({c['badge']})" if c.get("badge") else "")
            for c in creds
        )
        lines.append(f"Credentials: {rendered}")
    return "\n".join(lines) or "No structured facts provided."


def build_summary_prompt(profile: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Worker facts:\n{_facts_block(profile)}\n\nWrite the summary."},
    ]


def template_summary(profile: dict[str, Any]) -> str:
    """Deterministic fallback when the LLM is unavailable. Always factual."""
    name = profile.get("name") or "This worker"
    trade = profile.get("trade") or profile.get("program")
    loc = ", ".join(p for p in [profile.get("city"), profile.get("state")] if p)
    creds = profile.get("credentials") or []
    verified = [c for c in creds if c.get("badge") and c["badge"] != "Self-Reported"]

    parts: list[str] = []
    if trade:
        parts.append(f"{name} is training in {trade}" + (f", based in {loc}" if loc else "") + ".")
    else:
        parts.append(f"{name}" + (f" is based in {loc}" if loc else "") + ".")
    if verified:
        names = ", ".join(c["name"] for c in verified[:4])
        parts.append(
            f"They hold {len(verified)} verified credential"
            f"{'s' if len(verified) != 1 else ''}: {names}."
        )
    elif creds:
        parts.append(f"They have listed {len(creds)} credential{'s' if len(creds) != 1 else ''}.")
    if profile.get("willing_to_relocate"):
        parts.append("They are open to relocation.")
    if profile.get("available_from"):
        parts.append(f"Available from {profile['available_from']}.")
    return " ".join(parts).strip()


IMPACT_SYSTEM_PROMPT = (
    "You are writing a short impact-report narrative for a skilled-trades workforce "
    "nonprofit (SKILLED Foundation), for a board/donor audience. Use ONLY the metrics "
    "provided — never invent numbers, programs, or outcomes. 2 short paragraphs, "
    "confident and concrete, citing the exact figures given. No markdown, no headers."
)


def _pct(x: float | None) -> str:
    return f"{round(x * 100)}%" if isinstance(x, (int, float)) else "n/a"


def _money(x: int | None) -> str:
    return f"${x:,}" if isinstance(x, int) else "n/a"


def _impact_facts(numbers: dict[str, Any]) -> str:
    s = numbers.get("summary", {})
    lines = [
        f"Total served: {s.get('total_served')}",
        f"Placed in employment: {s.get('placed')} ({_pct(s.get('employment_rate'))})",
        f"Median placement wage: {_money(s.get('median_wage'))}",
        f"Credential attainment rate: {_pct(s.get('attainment_rate'))}",
        f"Median time to hire: {s.get('median_time_to_hire_days')} days",
    ]
    top = numbers.get("top_programs") or []
    if top:
        lines.append("Top programs by placement rate: " + "; ".join(
            f"{c['cohort']} ({_pct(c.get('employment_rate'))}, n={c['n']})" for c in top
        ))
    return "\n".join(lines)


def template_impact_report(numbers: dict[str, Any]) -> str:
    s = numbers.get("summary", {})
    served = s.get("total_served") or 0
    parts = [
        f"SKILLED Foundation served {served} learners across its skilled-trades programs. "
        f"{_pct(s.get('employment_rate'))} reached employment at a median reported wage of "
        f"{_money(s.get('median_wage'))}, with a {_pct(s.get('attainment_rate'))} credential "
        f"attainment rate and a median time to hire of {s.get('median_time_to_hire_days')} days."
    ]
    top = numbers.get("top_programs") or []
    if top:
        leader = top[0]
        parts.append(
            f"The {leader['cohort']} cohort led on placement at "
            f"{_pct(leader.get('employment_rate'))} (n={leader['n']}), demonstrating strong "
            "employer demand in that trade."
        )
    return " ".join(parts)


async def generate_impact_report(numbers: dict[str, Any]) -> tuple[str, str]:
    """Returns (narrative, source). Numbers are computed deterministically upstream;
    only the prose is AI-generated, with a factual template fallback."""
    api_key = get_settings().openai_api_key
    if not api_key:
        return template_impact_report(numbers), "template"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": get_settings().llm_extraction_model or "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": IMPACT_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Metrics:\n{_impact_facts(numbers)}\n\nWrite the narrative."},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 320,
                },
            )
        if resp.status_code != 200:
            return template_impact_report(numbers), "template"
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return (text or template_impact_report(numbers)), ("ai" if text else "template")
    except Exception as exc:  # pragma: no cover - network
        logger.warning("Impact report fell back to template: %s", exc)
        return template_impact_report(numbers), "template"


def template_employer_insights(n: dict[str, Any]) -> str:
    parts = [
        f"Across {n.get('hires', 0)} reported placement(s), median time to fill was "
        f"{n.get('time_to_fill_days')} days at a median wage of {_money(n.get('median_wage'))}."
    ]
    pm = n.get("platform_median_wage")
    mw = n.get("median_wage")
    if isinstance(pm, int) and isinstance(mw, int) and pm:
        delta = round((mw - pm) / pm * 100)
        parts.append(
            f"That is {abs(delta)}% {'above' if delta >= 0 else 'below'} the platform median "
            f"({_money(pm)}) for comparable roles."
        )
    if n.get("avg_match_fit") is not None:
        parts.append(
            f"Surfaced candidates averaged a {_pct(n['avg_match_fit'])} fit score, with "
            f"{n.get('strong_matches', 0)} strong matches in the pipeline."
        )
    return " ".join(parts)


async def generate_employer_insights(numbers: dict[str, Any]) -> tuple[str, str]:
    """AI narrative over an employer's hiring funnel + benchmarks; template fallback."""
    api_key = get_settings().openai_api_key
    if not api_key:
        return template_employer_insights(numbers), "template"
    facts = "\n".join(f"{k}: {v}" for k, v in numbers.items() if not isinstance(v, (list, dict)))
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": get_settings().llm_extraction_model or "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": (
                            "You write a 2-sentence hiring-analytics insight for an employer on a "
                            "skilled-trades platform. Use ONLY the metrics provided; never invent. "
                            "No markdown.")},
                        {"role": "user", "content": f"Metrics:\n{facts}\n\nWrite the insight."},
                    ],
                    "temperature": 0.4, "max_tokens": 180,
                },
            )
        if resp.status_code != 200:
            return template_employer_insights(numbers), "template"
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return (text or template_employer_insights(numbers)), ("ai" if text else "template")
    except Exception:  # pragma: no cover
        return template_employer_insights(numbers), "template"


async def generate_summary(profile: dict[str, Any]) -> tuple[str, str]:
    """
    Returns (summary_text, source) where source is "ai" or "template".
    Never raises — falls back to a deterministic template on any failure.
    """
    api_key = get_settings().openai_api_key
    if not api_key:
        return template_summary(profile), "template"

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": get_settings().llm_extraction_model or "gpt-4o-mini",
                    "messages": build_summary_prompt(profile),
                    "temperature": 0.4,
                    "max_tokens": 200,
                },
            )
        if resp.status_code != 200:
            logger.error("Summary LLM error %d: %s", resp.status_code, resp.text[:200])
            return template_summary(profile), "template"
        text = resp.json()["choices"][0]["message"]["content"].strip()
        return (text or template_summary(profile)), ("ai" if text else "template")
    except Exception as exc:  # pragma: no cover - network
        logger.warning("Summary generation fell back to template: %s", exc)
        return template_summary(profile), "template"
