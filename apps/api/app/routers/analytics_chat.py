"""
Analytics chat — small QA surface on top of the employer's analytics numbers.

POST /employer/me/analytics/chat
  body: { question: string }
  returns: { answer: string, examples: string[] }

Pulls the same underlying insights the analytics page uses, then asks the LLM
to answer the question in one or two sentences grounded in that data. Falls
back to a deterministic answer when no OpenAI key is configured, so the
feature works in dev.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import require_employer_or_admin
from app.auth.schemas import CurrentUser
from app.config import get_settings
from app.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/employer/me/analytics", tags=["employer"])


class ChatIn(BaseModel):
    question: str = Field(..., min_length=2, max_length=400)


class ChatOut(BaseModel):
    answer: str
    stubbed: bool = False


EXAMPLE_QUESTIONS = [
    "Which of my jobs is filling the fastest?",
    "How does my median wage compare to the platform?",
    "What percentage of applicants am I hiring?",
    "Which trade family had the most applicants this month?",
]


@router.get("/chat/examples", response_model=list[str])
async def chat_examples(_: CurrentUser = Depends(require_employer_or_admin)):
    return EXAMPLE_QUESTIONS


@router.post("/chat", response_model=ChatOut)
async def analytics_chat(body: ChatIn, user: CurrentUser = Depends(require_employer_or_admin)):
    async with get_db() as conn:
        emp = await conn.fetchrow(
            "SELECT employer_id FROM public.employer_contacts WHERE user_id = $1 LIMIT 1",
            user.user_id,
        )
        if not emp and user.role != "admin":
            raise HTTPException(status_code=404, detail="Employer profile not found.")
        employer_id = emp["employer_id"] if emp else None

        # Pull the same tallies the analytics page shows.
        counters = await conn.fetchrow(
            """
            SELECT
              (SELECT COUNT(*) FROM public.applications WHERE employer_id = $1) AS total_apps,
              (SELECT COUNT(*) FROM public.applications WHERE employer_id = $1 AND status = 'hired') AS hires,
              (SELECT COUNT(*) FROM public.applications WHERE employer_id = $1 AND status = 'rejected') AS rejections,
              (SELECT COUNT(*) FROM public.jobs WHERE employer_id = $1) AS jobs,
              (SELECT ROUND(EXTRACT(EPOCH FROM AVG(decision_at - submitted_at))/86400)
                 FROM public.applications WHERE employer_id = $1 AND status = 'hired' AND decision_at IS NOT NULL) AS avg_days_to_hire,
              (SELECT COUNT(*) FROM public.applications
                WHERE employer_id = $1 AND employer_viewed_at IS NULL
                  AND submitted_at < NOW() - INTERVAL '5 days') AS dormant_count
            """,
            employer_id,
        )

    context = {
        "total_applications": int(counters["total_apps"] or 0),
        "hires":               int(counters["hires"] or 0),
        "rejections":          int(counters["rejections"] or 0),
        "jobs_posted":         int(counters["jobs"] or 0),
        "avg_days_to_hire":    int(counters["avg_days_to_hire"] or 0),
        "dormant_awaiting_review": int(counters["dormant_count"] or 0),
    }

    settings = get_settings()
    if not settings.openai_api_key:
        return ChatOut(answer=_deterministic_answer(body.question, context), stubbed=True)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model=settings.llm_extraction_model,
            messages=[
                {"role": "system", "content":
                    "You are a data analyst inside SkillPointe. Answer the employer's question in ONE or TWO short sentences. "
                    "Use only the numbers provided; never invent facts. If the data is empty, say so plainly."},
                {"role": "user", "content": f"Employer data: {context}\n\nQuestion: {body.question}"},
            ],
            temperature=0.15,
            max_tokens=180,
        )
        answer = (resp.choices[0].message.content or "").strip()
        return ChatOut(answer=answer or _deterministic_answer(body.question, context), stubbed=False)
    except Exception as e:
        logger.warning(f"analytics chat LLM failed: {e}")
        return ChatOut(answer=_deterministic_answer(body.question, context), stubbed=True)


def _deterministic_answer(q: str, ctx: dict) -> str:
    """Best-effort answer without an LLM. Keeps the feature useful in dev."""
    ql = q.lower()
    if "hire" in ql and ctx["total_applications"]:
        rate = round(100 * ctx["hires"] / max(1, ctx["total_applications"]))
        return f"You've hired {ctx['hires']} of {ctx['total_applications']} applicants — {rate}% hire rate."
    if "time to hire" in ql or "how long" in ql:
        if ctx["avg_days_to_hire"]:
            return f"Your average is {ctx['avg_days_to_hire']} days from application to hire."
        return "Not enough hires yet to measure time-to-hire."
    if "dormant" in ql or "waiting" in ql or "response" in ql:
        n = ctx["dormant_awaiting_review"]
        if n == 0:
            return "You're responding to every applicant within five days — no dormant applications."
        return f"{n} application{'s are' if n != 1 else ' is'} waiting more than five days without a review."
    if "job" in ql:
        return f"You have {ctx['jobs_posted']} job{'s' if ctx['jobs_posted'] != 1 else ''} posted and {ctx['total_applications']} applications across them."
    return (
        f"Right now: {ctx['jobs_posted']} jobs posted, {ctx['total_applications']} applications, "
        f"{ctx['hires']} hires."
    )
