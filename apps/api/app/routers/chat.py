"""
chat.py — Applicant planning chat endpoints (Phase 8).

Endpoints:
  GET  /applicant/me/chat/sessions           — list sessions (most recent first)
  POST /applicant/me/chat/sessions           — create new session
  GET  /applicant/me/chat/sessions/{id}      — session + full message history
  POST /applicant/me/chat/sessions/{id}/messages — send message, get AI reply

All routes require an authenticated applicant.
Context is built from the applicant's current top matches at session creation.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import require_applicant
from app.auth.schemas import CurrentUser
from app.db import get_db
from app.services.chat import (
    generate_chat_response,
    _build_context_snapshot,
    _build_job_focused_snapshot,
    _generate_opening_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/applicant/me/chat", tags=["chat"])

_MAX_SESSIONS = 20
_MAX_MESSAGES = 200


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ChatSessionSummary(BaseModel):
    session_id: str
    title: str | None
    created_at: str
    message_count: int
    is_active: bool


class ChatMessageOut(BaseModel):
    message_id: str
    role: str  # 'user' | 'assistant'
    content: str
    created_at: str


class ChatSessionDetail(BaseModel):
    session_id: str
    title: str | None
    created_at: str
    is_active: bool
    messages: list[ChatMessageOut]


class SendMessageRequest(BaseModel):
    content: str


class CreateSessionRequest(BaseModel):
    title: str | None = None
    job_id: str | None = None  # when set, session is focused on this specific job


# ---------------------------------------------------------------------------
# GET /applicant/me/chat/sessions
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=list[ChatSessionSummary])
async def list_sessions(
    current_user: Annotated[CurrentUser, Depends(require_applicant)],
) -> list[ChatSessionSummary]:
    async with get_db() as conn:
        applicant_id = await _get_applicant_id(conn, current_user.user_id)
        rows = await conn.fetch(
            """
            SELECT
                cs.id::text AS session_id,
                cs.title,
                cs.created_at::text,
                cs.is_active,
                COUNT(cm.id) AS message_count
            FROM public.chat_sessions cs
            LEFT JOIN public.chat_messages cm ON cm.session_id = cs.id
            WHERE cs.applicant_id = $1
            GROUP BY cs.id
            ORDER BY cs.created_at DESC
            LIMIT $2
            """,
            applicant_id,
            _MAX_SESSIONS,
        )
    return [
        ChatSessionSummary(
            session_id=r["session_id"],
            title=r["title"],
            created_at=r["created_at"],
            is_active=bool(r["is_active"]),
            message_count=int(r["message_count"] or 0),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# POST /applicant/me/chat/sessions
# ---------------------------------------------------------------------------

@router.post("/sessions", response_model=ChatSessionSummary, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    current_user: Annotated[CurrentUser, Depends(require_applicant)],
) -> ChatSessionSummary:
    async with get_db() as conn:
        applicant_id = await _get_applicant_id(conn, current_user.user_id)

        # Fetch applicant profile (needed for both paths)
        profile_row = await conn.fetchrow(
            """
            SELECT first_name, last_name, program_name_raw, state, willing_to_relocate
            FROM public.applicants WHERE id = $1
            """,
            applicant_id,
        )
        profile = dict(profile_row) if profile_row else {}

        opening_message: str | None = None

        if body.job_id:
            # Job-focused session: build snapshot around one specific job
            job_row = await conn.fetchrow(
                """
                SELECT j.id, j.title_normalized, j.title_raw, j.city, j.state,
                       j.work_setting::text AS work_setting,
                       e.name AS employer_name
                FROM public.jobs j
                JOIN public.employers e ON e.id = j.employer_id
                WHERE j.id = $1::uuid AND j.is_active = TRUE
                """,
                body.job_id,
            )
            if not job_row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

            job = dict(job_row)

            match_row = await conn.fetchrow(
                """
                SELECT policy_adjusted_score, eligibility_status::text,
                       top_strengths, top_gaps, required_missing_items, recommended_next_step
                FROM public.matches
                WHERE applicant_id = $1 AND job_id = $2::uuid
                  AND is_visible_to_applicant = TRUE
                LIMIT 1
                """,
                applicant_id,
                body.job_id,
            )
            match = dict(match_row) if match_row else None

            snapshot = _build_job_focused_snapshot(profile, job, match)
            job_title = job.get("title_normalized") or job.get("title_raw") or "job"
            employer_name = job.get("employer_name") or ""
            title = body.title or f"Planning chat — {job_title} at {employer_name}"
            opening_message = _generate_opening_message(snapshot)
        else:
            # General session: build snapshot from top matches
            match_rows = await conn.fetch(
                """
                SELECT
                    j.title_normalized AS job_title,
                    e.name AS employer_name,
                    m.policy_adjusted_score,
                    m.eligibility_status::text,
                    m.top_strengths,
                    m.top_gaps,
                    m.recommended_next_step
                FROM public.matches m
                JOIN public.jobs j ON j.id = m.job_id
                JOIN public.employers e ON e.id = j.employer_id
                WHERE m.applicant_id = $1
                  AND m.is_visible_to_applicant = TRUE
                  AND m.eligibility_status IN ('eligible', 'near_fit')
                ORDER BY m.policy_adjusted_score DESC NULLS LAST
                LIMIT 10
                """,
                applicant_id,
            )
            matches = [dict(r) for r in match_rows]
            snapshot = _build_context_snapshot(profile, matches)
            title = body.title or _auto_title(snapshot)

        row = await conn.fetchrow(
            """
            INSERT INTO public.chat_sessions (applicant_id, title, context_snapshot)
            VALUES ($1, $2, $3::jsonb)
            RETURNING id::text AS id, title, created_at::text, is_active
            """,
            applicant_id,
            title,
            snapshot,
        )

        # Insert the opening assistant message for job-focused sessions
        if opening_message:
            await conn.execute(
                """
                INSERT INTO public.chat_messages (session_id, role, content)
                VALUES ($1::uuid, 'assistant', $2)
                """,
                row["id"],
                opening_message,
            )

    return ChatSessionSummary(
        session_id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        is_active=bool(row["is_active"]),
        message_count=1 if opening_message else 0,
    )


# ---------------------------------------------------------------------------
# GET /applicant/me/chat/sessions/{session_id}
# ---------------------------------------------------------------------------

@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_session(
    session_id: str,
    current_user: Annotated[CurrentUser, Depends(require_applicant)],
) -> ChatSessionDetail:
    async with get_db() as conn:
        applicant_id = await _get_applicant_id(conn, current_user.user_id)
        session_row = await conn.fetchrow(
            """
            SELECT id::text, title, created_at::text, is_active
            FROM public.chat_sessions
            WHERE id = $1::uuid AND applicant_id = $2
            """,
            session_id,
            applicant_id,
        )
        if not session_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        msg_rows = await conn.fetch(
            """
            SELECT id::text AS message_id, role::text, content, created_at::text
            FROM public.chat_messages
            WHERE session_id = $1::uuid
            ORDER BY created_at ASC
            LIMIT $2
            """,
            session_id,
            _MAX_MESSAGES,
        )

    return ChatSessionDetail(
        session_id=session_row["id"],
        title=session_row["title"],
        created_at=session_row["created_at"],
        is_active=bool(session_row["is_active"]),
        messages=[
            ChatMessageOut(
                message_id=r["message_id"],
                role=r["role"],
                content=r["content"],
                created_at=r["created_at"],
            )
            for r in msg_rows
        ],
    )


# ---------------------------------------------------------------------------
# POST /applicant/me/chat/sessions/{session_id}/messages
# ---------------------------------------------------------------------------

@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageOut,
    status_code=201,
)
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    current_user: Annotated[CurrentUser, Depends(require_applicant)],
) -> ChatMessageOut:
    if not body.content.strip():
        raise HTTPException(status_code=422, detail="Message content cannot be empty")

    async with get_db() as conn:
        applicant_id = await _get_applicant_id(conn, current_user.user_id)

        # Verify session ownership
        session_row = await conn.fetchrow(
            """
            SELECT context_snapshot
            FROM public.chat_sessions
            WHERE id = $1::uuid AND applicant_id = $2 AND is_active = TRUE
            """,
            session_id,
            applicant_id,
        )
        if not session_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or closed",
            )

        context_snapshot: dict[str, Any] = session_row["context_snapshot"] or {}

        # Fetch recent message history for LLM context
        history_rows = await conn.fetch(
            """
            SELECT role::text, content
            FROM public.chat_messages
            WHERE session_id = $1::uuid
            ORDER BY created_at ASC
            """,
            session_id,
        )
        history = [{"role": r["role"], "content": r["content"]} for r in history_rows]

        # Store user message
        await conn.execute(
            """
            INSERT INTO public.chat_messages (session_id, role, content)
            VALUES ($1::uuid, 'user', $2)
            """,
            session_id,
            body.content,
        )

        # Log engagement event
        await conn.execute(
            """
            INSERT INTO public.engagement_events (applicant_id, event_type, event_data)
            VALUES ($1, 'chat_message_sent', $2::jsonb)
            """,
            applicant_id,
            {"session_id": session_id},
        )

    # Generate LLM response (outside the DB connection to avoid holding it open)
    try:
        ai_text = await generate_chat_response(
            session_id=session_id,
            user_message=body.content,
            history=history,
            context_snapshot=context_snapshot,
        )
    except RuntimeError:
        ai_text = "I'm having trouble generating a response right now. Please try again in a moment."

    async with get_db() as conn:
        msg_row = await conn.fetchrow(
            """
            INSERT INTO public.chat_messages (session_id, role, content, llm_model)
            VALUES ($1::uuid, 'assistant', $2, 'gpt-4o-mini')
            RETURNING id::text AS message_id, role::text, content, created_at::text
            """,
            session_id,
            ai_text,
        )

    return ChatMessageOut(
        message_id=msg_row["message_id"],
        role=msg_row["role"],
        content=msg_row["content"],
        created_at=msg_row["created_at"],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_applicant_id(conn: Any, user_id: str) -> Any:
    applicant_id = await conn.fetchval(
        "SELECT id FROM public.applicants WHERE user_id = $1", user_id
    )
    if not applicant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Applicant profile not found",
        )
    return applicant_id


def _auto_title(snapshot: dict[str, Any]) -> str:
    matches = snapshot.get("top_matches", [])
    if matches:
        return f"Planning chat — {matches[0].get('job_title', 'job search')}"
    return "Career planning chat"
