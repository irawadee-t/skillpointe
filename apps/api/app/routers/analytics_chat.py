"""
Analytics chat — small QA surface on top of the employer's analytics numbers.

POST /employer/me/analytics/chat
  body: { question: string }
  returns: { answer: string, stubbed: bool }

POST /employer/me/analytics/chat/stream
  Same pipeline, delivered as Server-Sent Events (buffer-then-stream): the
  full grounding + answer pipeline runs to completion FIRST, then the
  validated text is paced out as `chunk` frames and one terminal `done` frame
  (see app.util.sse). Errors surface as plain HTTP before any SSE byte, so
  the client can fall back to the JSON endpoint.

Pulls the same underlying insights the analytics page uses, then asks the LLM
to answer the question in one or two sentences grounded in that data. Falls
back to a deterministic answer when no OpenAI key is configured, so the
feature works in dev.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import require_employer_or_admin
from app.auth.schemas import CurrentUser
from app.config import get_settings
from app.db import get_db
from app.util.sse import SSE_HEADERS, paced_text_stream

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


async def _answer_question(body: ChatIn, user: CurrentUser) -> ChatOut:
    """Shared core for the JSON and SSE endpoints.

    Runs the FULL pipeline to completion — grounding SQL (the same definitions
    the analytics page uses), then LLM or deterministic answer — and returns
    the finished ChatOut. The SSE endpoint streams the returned text AFTER
    this completes (buffer-then-stream), so what streams is exactly what the
    JSON endpoint would have returned.
    """
    async with get_db() as conn:
        emp = await conn.fetchrow(
            "SELECT employer_id FROM public.employer_contacts WHERE user_id = $1 LIMIT 1",
            user.user_id,
        )
        if not emp and user.role != "admin":
            raise HTTPException(status_code=404, detail="Employer profile not found.")
        employer_id = emp["employer_id"] if emp else None

        # Grounding data = the SAME definitions the analytics page uses
        # (GET /employer/me/analytics), plus application-pipeline tallies.
        # Never re-derive a metric here with a different query than the page —
        # the chat must quote the numbers the employer is looking at.
        # "Applied" throughout this surface = a row in public.applications
        # (the inbox's table); saved_jobs interest is labeled self-reported.
        counters = await conn.fetchrow(
            """
            SELECT
              -- Tiles on /employer/analytics (identical predicates):
              (SELECT COUNT(*) FROM public.employer_outreach
                WHERE employer_id = $1 AND status = 'sent') AS outreach_sent,
              (SELECT COUNT(DISTINCT sj.applicant_id)
                 FROM public.saved_jobs sj
                 JOIN public.jobs j ON j.id = sj.job_id
                WHERE j.employer_id = $1
                  AND sj.interest_level = 'interested') AS candidates_interested,
              (SELECT COUNT(DISTINCT sj.applicant_id)
                 FROM public.saved_jobs sj
                 JOIN public.jobs j ON j.id = sj.job_id
                WHERE j.employer_id = $1
                  AND sj.interest_level = 'applied') AS self_reported_applied,
              (SELECT COUNT(*) FROM public.hire_outcomes
                WHERE employer_id = $1 AND outcome_type = 'hired') AS hires,
              -- Application pipeline (same predicates as the inbox buckets):
              (SELECT COUNT(*) FROM public.applications WHERE employer_id = $1) AS total_apps,
              (SELECT COUNT(*) FROM public.applications
                WHERE employer_id = $1 AND status = 'hired') AS hired_apps,
              (SELECT COUNT(*) FROM public.jobs WHERE employer_id = $1) AS jobs,
              (SELECT ROUND(EXTRACT(EPOCH FROM AVG(decision_at - submitted_at))/86400)
                 FROM public.applications WHERE employer_id = $1 AND status = 'hired' AND decision_at IS NOT NULL) AS avg_days_to_hire,
              -- Wage benchmark (same queries as /employer/me/analytics/insights):
              (SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY reported_wage_annual)
                 FROM public.hire_outcomes
                WHERE employer_id = $1 AND reported_wage_annual IS NOT NULL) AS median_wage,
              (SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY reported_wage_annual)
                 FROM public.hire_outcomes
                WHERE reported_wage_annual IS NOT NULL) AS platform_median_wage,
              -- Same dormancy definition as GET /admin/analytics/sla
              -- (5-day threshold, still-open statuses only):
              (SELECT COUNT(*) FROM public.applications
                WHERE employer_id = $1 AND employer_viewed_at IS NULL
                  AND status IN ('submitted', 'reviewed')
                  AND submitted_at < NOW() - INTERVAL '5 days') AS dormant_count
            """,
            employer_id,
        )

        # "Which job is filling fastest" = applications per job over the last
        # 30 days — a real, deterministic SQL answer.
        fastest_rows = await conn.fetch(
            """
            SELECT COALESCE(j.title_normalized, j.title_raw) AS title, COUNT(*) AS n
            FROM public.applications a
            JOIN public.jobs j ON j.id = a.job_id
            WHERE a.employer_id = $1
              AND a.submitted_at >= NOW() - INTERVAL '30 days'
            GROUP BY 1
            ORDER BY n DESC
            LIMIT 3
            """,
            employer_id,
        )

        # "Which trade family had the most applicants this month" — applicants
        # who applied this calendar month, grouped by the job's trade family.
        trade_rows = await conn.fetch(
            """
            SELECT COALESCE(jf.name, 'Uncategorized') AS family,
                   COUNT(DISTINCT a.applicant_id) AS n
            FROM public.applications a
            JOIN public.jobs j ON j.id = a.job_id
            LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
            WHERE a.employer_id = $1
              AND a.submitted_at >= date_trunc('month', NOW())
            GROUP BY 1
            ORDER BY n DESC
            LIMIT 3
            """,
            employer_id,
        )

    context = {
        "outreach_sent":        int(counters["outreach_sent"] or 0),
        "candidates_interested": int(counters["candidates_interested"] or 0),
        "self_reported_applied": int(counters["self_reported_applied"] or 0),
        "hires_reported":       int(counters["hires"] or 0),
        "total_applications":   int(counters["total_apps"] or 0),
        "hired_applications":   int(counters["hired_apps"] or 0),
        "jobs_posted":          int(counters["jobs"] or 0),
        "avg_days_to_hire":     int(counters["avg_days_to_hire"] or 0),
        "median_wage":          int(counters["median_wage"]) if counters["median_wage"] is not None else None,
        "platform_median_wage": int(counters["platform_median_wage"]) if counters["platform_median_wage"] is not None else None,
        "dormant_awaiting_review": int(counters["dormant_count"] or 0),
        "fastest_jobs_30d":     [(r["title"], int(r["n"])) for r in fastest_rows],
        "top_trades_this_month": [(r["family"], int(r["n"])) for r in trade_rows],
    }

    settings = get_settings()
    if not settings.openai_api_key:
        return ChatOut(answer=_deterministic_answer(body.question, context), stubbed=True)

    try:
        from app.util.openai_client import get_openai_client
        client = get_openai_client()  # bounded timeout + one retry (not the SDK's 600s default)
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


@router.post("/chat", response_model=ChatOut)
async def analytics_chat(body: ChatIn, user: CurrentUser = Depends(require_employer_or_admin)):
    return await _answer_question(body, user)


@router.post("/chat/stream")
async def analytics_chat_stream(
    body: ChatIn, user: CurrentUser = Depends(require_employer_or_admin)
) -> StreamingResponse:
    """Same pipeline as POST /chat, delivered as Server-Sent Events.

    Answers here are deterministic SQL (or a short grounded LLM sentence), so
    this is pure buffer-then-stream: the complete validated answer exists
    before the first byte, and pacing only makes delivery progressive. Any
    error (404 employer profile, 422 validation) is a plain HTTP error — the
    client falls back to the JSON endpoint on those.

        event: chunk  data: {"delta": "..."}   (repeated)
        event: done   data: {ChatOut}          (terminal)
    """
    out = await _answer_question(body, user)
    return StreamingResponse(
        paced_text_stream(out.answer, out.model_dump()),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _deterministic_answer(q: str, ctx: dict) -> str:
    """SQL-backed answers, no LLM required. Each suggested question on the
    analytics page routes to real math over real rows; only free-form
    questions fall through to the generic summary at the bottom."""
    ql = q.lower()

    # "Which of my jobs is filling the fastest?"
    if "filling" in ql or "fastest" in ql:
        fastest = ctx.get("fastest_jobs_30d") or []
        if not fastest:
            return "No applications in the last 30 days, so no job is filling faster than another yet."
        lead = fastest[0]
        answer = f"Over the last 30 days, {lead[0]} received the most applications ({_plural(lead[1], 'application')})."
        if len(fastest) > 1:
            rest = ", ".join(f"{t} ({n})" for t, n in fastest[1:])
            answer += f" Next: {rest}."
        return answer

    # "How does my median wage compare to the platform?"
    if "wage" in ql or "salary" in ql or "pay" in ql:
        mw, pm = ctx.get("median_wage"), ctx.get("platform_median_wage")
        if mw is None:
            return "No reported wages on your hires yet. Report a wage when marking hires to see the benchmark."
        if not pm:
            return f"Your median reported wage is ${mw:,}; the platform benchmark isn't available yet."
        delta = round((mw - pm) / pm * 100)
        direction = "above" if delta >= 0 else "below"
        return f"Your median reported wage is ${mw:,} vs the platform median ${pm:,}, {abs(delta)}% {direction}."

    # "What percentage of applicants am I hiring?" — hires ÷ applications,
    # both from public.applications (the inbox's table), math shown.
    if ("hire" in ql or "hiring" in ql) and ("%" in ql or "percent" in ql or "rate" in ql or "applicant" in ql):
        total, hired = ctx["total_applications"], ctx["hired_applications"]
        if total == 0:
            return "No applications yet, so there's no hire rate to compute."
        rate = round(100 * hired / total)
        return f"You've hired {hired} of {_plural(total, 'application')}, a {rate}% hire rate ({hired} ÷ {total})."

    # "Which trade family had the most applicants this month?"
    if "trade" in ql or "family" in ql:
        trades = ctx.get("top_trades_this_month") or []
        if not trades:
            return "No applicants this month yet, so no trade family leads."
        lead = trades[0]
        answer = f"This month, {lead[0]} drew the most applicants ({_plural(lead[1], 'applicant')})."
        if len(trades) > 1:
            rest = ", ".join(f"{t} ({n})" for t, n in trades[1:])
            answer += f" Then: {rest}."
        return answer

    if "time to hire" in ql or "how long" in ql:
        if ctx["avg_days_to_hire"]:
            return f"Your average is {ctx['avg_days_to_hire']} days from application to hire."
        return "Not enough hires yet to measure time-to-hire."
    if "dormant" in ql or "waiting" in ql or "response" in ql:
        n = ctx["dormant_awaiting_review"]
        if n == 0:
            return "You're responding to every applicant within five days. No dormant applications."
        return f"{n} application{'s are' if n != 1 else ' is'} waiting more than five days without a review."
    if "outreach" in ql or "reach" in ql:
        return f"You've logged {_plural(ctx['outreach_sent'], 'outreach message')}."
    if "interest" in ql:
        return (
            f"{_plural(ctx['candidates_interested'], 'candidate')} marked interest in your jobs "
            f"and {ctx['self_reported_applied']} said they applied (self-reported); "
            f"{_plural(ctx['total_applications'], 'application')} actually arrived in your inbox."
        )
    if "hire" in ql and ctx["total_applications"]:
        hired = ctx["hired_applications"]
        return f"You've hired {hired} of {_plural(ctx['total_applications'], 'application')}."
    if "job" in ql:
        return (
            f"You have {_plural(ctx['jobs_posted'], 'job')} posted and "
            f"{_plural(ctx['total_applications'], 'application')} across them."
        )
    return (
        f"Right now: {_plural(ctx['jobs_posted'], 'job')} posted, "
        f"{_plural(ctx['total_applications'], 'application')}, "
        f"{_plural(ctx['outreach_sent'], 'outreach message')} logged, "
        f"{_plural(ctx['hired_applications'], 'hire')}."
    )
