"""
chat.py — Applicant planning chat service (Phase 8).

Builds context from the applicant's top matches, then calls the LLM
to produce a grounded, actionable response.

The LLM is supporting — it sees structured match data and explains
or advises; it does NOT modify scores or rankings.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a career planning advisor for SkillPointe, a skilled-trades workforce platform.
You are helping an applicant who is enrolled in or completing a skilled-trades training program.

Your role:
- Answer questions about their job matches, skill gaps, and next steps
- Be encouraging but honest about gaps
- Focus on actionable advice (certifications to earn, experience to seek, etc.)
- Reference the specific matches, strengths, and gaps provided in the context
- Do NOT make up job listings or employers not in the context
- Keep responses concise (3–5 sentences unless a list is more useful)
- Do not claim to schedule interviews or apply on their behalf

You must NOT:
- Fabricate match scores or gap descriptions not present in the context
- Recommend specific external websites unless clearly appropriate
- Make promises about hiring outcomes
"""


def _build_context_snapshot(
    profile: dict[str, Any],
    matches: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the context snapshot stored at session creation time."""
    top_matches = [
        {
            "job_title": m.get("job_title"),
            "employer": m.get("employer_name"),
            "score": float(m["policy_adjusted_score"]) if m.get("policy_adjusted_score") is not None else None,
            "status": m.get("eligibility_status"),
            "top_strengths": m.get("top_strengths", [])[:3],
            "top_gaps": m.get("top_gaps", [])[:3],
            "recommended_next_step": m.get("recommended_next_step"),
        }
        for m in matches[:5]
    ]
    return {
        "applicant_name": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
        "program": profile.get("program_name_raw"),
        "state": profile.get("state"),
        "willing_to_relocate": profile.get("willing_to_relocate"),
        "top_matches": top_matches,
        "total_eligible": sum(1 for m in matches if m.get("eligibility_status") == "eligible"),
        "total_near_fit": sum(1 for m in matches if m.get("eligibility_status") == "near_fit"),
    }


def _build_user_context_block(snapshot: dict[str, Any]) -> str:
    """Convert the context snapshot to a readable block for the LLM."""
    lines = [
        f"Applicant: {snapshot.get('applicant_name', 'Unknown')}",
        f"Program: {snapshot.get('program', 'Not set')}",
        f"State: {snapshot.get('state', 'Not set')}",
        f"Willing to relocate: {snapshot.get('willing_to_relocate', False)}",
        f"Eligible matches: {snapshot.get('total_eligible', 0)}",
        f"Near-fit matches: {snapshot.get('total_near_fit', 0)}",
        "",
        "Top job matches:",
    ]
    for i, m in enumerate(snapshot.get("top_matches", []), 1):
        lines.append(f"  {i}. {m['job_title']} at {m['employer']} — score {m['score']}, {m['status']}")
        if m.get("top_strengths"):
            lines.append(f"     Strengths: {'; '.join(m['top_strengths'][:2])}")
        if m.get("top_gaps"):
            lines.append(f"     Gaps: {'; '.join(m['top_gaps'][:2])}")
        if m.get("recommended_next_step"):
            lines.append(f"     Suggested: {m['recommended_next_step']}")
    return "\n".join(lines)


async def generate_chat_response(
    session_id: str,
    user_message: str,
    history: list[dict[str, Any]],
    context_snapshot: dict[str, Any],
) -> str:
    """
    Call OpenAI to generate a planning chat response.
    Returns the assistant text content.
    Raises RuntimeError if the API call fails.
    """
    api_key = get_settings().openai_api_key
    if not api_key:
        return (
            "I'm sorry — the AI advisor is not configured on this server. "
            "Please contact a SkillPointe administrator."
        )

    context_block = _build_user_context_block(context_snapshot)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": f"[Current applicant context]\n{context_block}",
        },
    ]

    # Add prior turns (skip system messages)
    for turn in history[-10:]:  # last 10 turns to stay within context
        if turn["role"] in ("user", "assistant"):
            messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_message})

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 500,
                },
            )
        if resp.status_code != 200:
            logger.error("OpenAI error %d: %s", resp.status_code, resp.text[:200])
            raise RuntimeError(f"OpenAI API error {resp.status_code}")

        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    except Exception as exc:
        logger.exception("Chat LLM call failed for session %s: %s", session_id, exc)
        raise RuntimeError("Failed to generate response") from exc


def _build_job_focused_snapshot(
    profile: dict[str, Any],
    job: dict[str, Any],
    match: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build context snapshot focused on one specific job."""
    score = None
    if match and match.get("policy_adjusted_score") is not None:
        score = float(match["policy_adjusted_score"])
    return {
        "mode": "job_focused",
        "applicant_name": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
        "program": profile.get("program_name_raw"),
        "state": profile.get("state"),
        "willing_to_relocate": profile.get("willing_to_relocate"),
        "focused_job": {
            "job_id": str(job.get("id", "")),
            "job_title": job.get("title_normalized") or job.get("title_raw"),
            "employer": job.get("employer_name"),
            "city": job.get("city"),
            "state": job.get("state"),
            "work_setting": job.get("work_setting"),
            "score": score,
            "status": match.get("eligibility_status") if match else None,
            "top_strengths": list(match.get("top_strengths") or [])[:5] if match else [],
            "top_gaps": list(match.get("top_gaps") or [])[:5] if match else [],
            "required_missing_items": list(match.get("required_missing_items") or [])[:5] if match else [],
            "recommended_next_step": match.get("recommended_next_step") if match else None,
        },
    }


def _generate_opening_message(snapshot: dict[str, Any]) -> str:
    """Generate a template opening message for a job-focused chat session."""
    job = snapshot.get("focused_job", {})
    name = snapshot.get("applicant_name", "")
    greeting = f"Hi {name}!" if name else "Hi!"

    title = job.get("job_title") or "this position"
    employer = job.get("employer") or "the employer"
    score = job.get("score")
    status = job.get("status")
    strengths = job.get("top_strengths") or []
    gaps = job.get("top_gaps") or []
    missing = job.get("required_missing_items") or []
    next_step = job.get("recommended_next_step")

    lines = [f"{greeting} Let's talk about the **{title}** position at **{employer}**.", ""]

    if score is not None and status:
        status_label = {"eligible": "Eligible ✓", "near_fit": "Near Fit"}.get(status, status)
        lines += [f"**Match score:** {round(score)}/100 — {status_label}", ""]

    if strengths:
        lines.append("**Your strengths for this role:**")
        for s in strengths[:3]:
            lines.append(f"- {s}")
        lines.append("")

    all_gaps = list(dict.fromkeys(list(gaps) + list(missing)))  # dedupe, preserve order
    if all_gaps:
        lines.append("**Gaps to work on:**")
        for g in all_gaps[:3]:
            lines.append(f"- {g}")
        lines.append("")

    if next_step:
        lines += [f"**Suggested next step:** {next_step}", ""]

    if score is None:
        lines += [
            "I don't have a formal match score for this job yet, but I can still help you "
            "think through how your background aligns and what you might need to prepare.",
            "",
        ]

    lines.append(
        "What would you like to know? I can help with certifications to pursue, "
        "how to frame your experience, or what to expect from the hiring process."
    )
    return "\n".join(lines)


async def generate_outreach_draft(
    job_title: str,
    employer_name: str,
    applicant_name: str,
    top_strengths: list[str],
    recommended_next_step: str | None,
) -> dict[str, str]:
    """
    Generate an AI-drafted outreach message from an employer to a matched candidate.
    Returns {'subject': ..., 'body': ...}.
    """
    api_key = get_settings().openai_api_key
    if not api_key:
        return {
            "subject": f"Opportunity: {job_title} at {employer_name}",
            "body": (
                f"Dear {applicant_name},\n\n"
                f"We noticed your profile and believe you could be a great fit for our {job_title} position. "
                f"We would love to connect with you to discuss this opportunity.\n\n"
                f"Best regards,\n{employer_name}"
            ),
        }

    strengths_text = "; ".join(top_strengths[:3]) if top_strengths else "your skills and training"
    prompt = (
        f"Write a short, professional outreach message from an employer named '{employer_name}' "
        f"to a job candidate named '{applicant_name}' for a '{job_title}' position.\n\n"
        f"Key strengths identified: {strengths_text}.\n"
        f"{'Suggested next step: ' + recommended_next_step if recommended_next_step else ''}\n\n"
        f"Output JSON with keys 'subject' (email subject line) and 'body' (email body, 3-4 sentences, "
        f"professional but warm). Do not include a salutation line — start with 'I came across'."
    )

    try:
        import httpx
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.6,
                    "max_tokens": 300,
                    "response_format": {"type": "json_object"},
                },
            )
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI error {resp.status_code}")

        data = resp.json()
        result = json.loads(data["choices"][0]["message"]["content"])
        return {
            "subject": result.get("subject", f"Opportunity: {job_title}"),
            "body": result.get("body", ""),
        }
    except Exception as exc:
        logger.exception("Outreach draft generation failed: %s", exc)
        return {
            "subject": f"Opportunity: {job_title} at {employer_name}",
            "body": (
                f"Dear {applicant_name},\n\n"
                f"We would like to discuss the {job_title} position with you. "
                f"Your background in {strengths_text} stood out to us.\n\n"
                f"Best regards,\n{employer_name}"
            ),
        }
