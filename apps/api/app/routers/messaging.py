"""
messaging.py — Direct messaging between applicants and employers.

Endpoints (role-sensitive, determined from JWT):
  GET  /conversations                       — list my conversations
  POST /conversations                       — start or resume a conversation
  GET  /conversations/{id}/messages         — fetch messages (newest 100)
  POST /conversations/{id}/messages         — send a message
  POST /conversations/{id}/read             — mark conversation as read

Employers can initiate; applicants can reply (or also initiate).
All DM activity is recorded as engagement_events for admin analytics.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.auth.dependencies import require_authenticated
from app.auth.schemas import CurrentUser
from app.db import get_db
from app.skilled_pro.notifications import notify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["messaging"])

_MAX_MESSAGES = 100


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ConversationSummary(BaseModel):
    conversation_id: str
    other_party_name: str   # employer name (for applicant) or applicant name (for employer)
    job_title: str | None
    last_message_at: str
    unread_count: int
    message_count: int
    last_message_preview: str | None = None  # trimmed snippet of the newest message


class DirectMessageOut(BaseModel):
    message_id: str
    sender_role: str  # 'employer' | 'applicant'
    content: str
    created_at: str
    is_mine: bool   # True if the current user sent this message


class ConversationDetail(BaseModel):
    conversation_id: str
    other_party_name: str
    job_title: str | None
    messages: list[DirectMessageOut]


class StartConversationRequest(BaseModel):
    applicant_id: str | None = None   # required when employer starts
    employer_id: str | None = None    # required when applicant starts
    job_id: str | None = None
    match_id: str | None = None
    initial_message: str | None = Field(default=None, max_length=5000)


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)

    @field_validator("content")
    @classmethod
    def _content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_ids(conn: Any, user: CurrentUser) -> tuple[str, str, str]:
    """Return (role, applicant_id_or_none, employer_id_or_none)."""
    role = user.role
    if role == "applicant":
        applicant_id = await conn.fetchval(
            "SELECT id::text FROM public.applicants WHERE user_id = $1", user.user_id
        )
        if not applicant_id:
            raise HTTPException(status_code=404, detail="Applicant profile not found")
        return role, applicant_id, None
    elif role in ("employer", "admin"):
        employer_id = await conn.fetchval(
            "SELECT employer_id::text FROM public.employer_contacts WHERE user_id = $1", user.user_id
        )
        if not employer_id:
            raise HTTPException(status_code=404, detail="Employer profile not found")
        return role, None, employer_id
    else:
        raise HTTPException(status_code=403, detail="Role not permitted")


def _preview(content: str | None, limit: int = 120) -> str | None:
    """One-line snippet of the newest message for inbox rows."""
    if not content:
        return None
    flat = " ".join(content.split())
    return flat[: limit - 1] + "…" if len(flat) > limit else flat


# ---------------------------------------------------------------------------
# GET /conversations
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> list[ConversationSummary]:
    async with get_db() as conn:
        role, applicant_id, employer_id = await _resolve_ids(conn, current_user)

        if role == "applicant":
            rows = await conn.fetch(
                """
                SELECT
                    c.id::text AS conversation_id,
                    e.name AS other_party_name,
                    COALESCE(j.title_normalized, j.title_raw) AS job_title,
                    c.last_message_at::text,
                    c.applicant_unread AS unread_count,
                    COUNT(dm.id) AS message_count,
                    (SELECT dm2.content FROM public.direct_messages dm2
                      WHERE dm2.conversation_id = c.id
                      ORDER BY dm2.created_at DESC LIMIT 1) AS last_message_preview
                FROM public.conversations c
                JOIN public.employers e ON e.id = c.employer_id
                LEFT JOIN public.jobs j ON j.id = c.job_id
                LEFT JOIN public.direct_messages dm ON dm.conversation_id = c.id
                WHERE c.applicant_id = $1::uuid
                GROUP BY c.id, e.name, j.title_normalized, j.title_raw
                ORDER BY c.last_message_at DESC
                """,
                applicant_id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT
                    c.id::text AS conversation_id,
                    CONCAT(a.first_name, ' ', a.last_name) AS other_party_name,
                    COALESCE(j.title_normalized, j.title_raw) AS job_title,
                    c.last_message_at::text,
                    c.employer_unread AS unread_count,
                    COUNT(dm.id) AS message_count,
                    (SELECT dm2.content FROM public.direct_messages dm2
                      WHERE dm2.conversation_id = c.id
                      ORDER BY dm2.created_at DESC LIMIT 1) AS last_message_preview
                FROM public.conversations c
                JOIN public.applicants a ON a.id = c.applicant_id
                LEFT JOIN public.jobs j ON j.id = c.job_id
                LEFT JOIN public.direct_messages dm ON dm.conversation_id = c.id
                WHERE c.employer_id = $1::uuid
                GROUP BY c.id, a.first_name, a.last_name, j.title_normalized, j.title_raw
                ORDER BY c.last_message_at DESC
                """,
                employer_id,
            )

    return [
        ConversationSummary(
            conversation_id=r["conversation_id"],
            other_party_name=(r["other_party_name"] or "").strip() or "Unknown",
            job_title=r["job_title"],
            last_message_at=r["last_message_at"],
            unread_count=int(r["unread_count"] or 0),
            message_count=int(r["message_count"] or 0),
            last_message_preview=_preview(r["last_message_preview"]),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# POST /conversations
# ---------------------------------------------------------------------------

@router.post("", response_model=ConversationSummary, status_code=201)
async def start_conversation(
    body: StartConversationRequest,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> ConversationSummary:
    """Start a new conversation or return the existing one for the same pair+job."""
    async with get_db() as conn:
        role, my_applicant_id, my_employer_id = await _resolve_ids(conn, current_user)

        if role == "applicant":
            if not body.employer_id:
                raise HTTPException(status_code=422, detail="employer_id required")
            applicant_id = my_applicant_id
            employer_id = body.employer_id
        else:
            if not body.applicant_id:
                raise HTTPException(status_code=422, detail="applicant_id required")
            applicant_id = body.applicant_id
            employer_id = my_employer_id
            # Invariant: an employer may only start a conversation with an
            # applicant surfaced for one of THEIR jobs (a real match, or one
            # who applied). Without this an employer could message any
            # applicant by id, and stamp the row with a foreign job/match id.
            surfaced = await conn.fetchval(
                """
                SELECT 1
                  FROM public.matches m
                  JOIN public.jobs j ON j.id = m.job_id
                 WHERE m.applicant_id = $1::uuid
                   AND j.employer_id = $2::uuid
                   AND m.eligibility_status IN ('eligible', 'near_fit')
                 LIMIT 1
                """,
                applicant_id, employer_id,
            )
            if not surfaced:
                surfaced = await conn.fetchval(
                    """SELECT 1 FROM public.applications
                        WHERE applicant_id = $1::uuid AND employer_id = $2::uuid LIMIT 1""",
                    applicant_id, employer_id,
                )
            if not surfaced:
                raise HTTPException(
                    status_code=403,
                    detail="You can only message applicants surfaced for your jobs.",
                )
            # A job_id/match_id, when supplied, must belong to this employer.
            if body.job_id:
                owns_job = await conn.fetchval(
                    "SELECT 1 FROM public.jobs WHERE id = $1::uuid AND employer_id = $2::uuid",
                    body.job_id, employer_id,
                )
                if not owns_job:
                    raise HTTPException(status_code=403, detail="That job is not yours.")
            if body.match_id:
                owns_match = await conn.fetchval(
                    """SELECT 1 FROM public.matches m JOIN public.jobs j ON j.id = m.job_id
                        WHERE m.id = $1::uuid AND j.employer_id = $2::uuid""",
                    body.match_id, employer_id,
                )
                if not owns_match:
                    raise HTTPException(status_code=403, detail="That match is not yours.")

        # Find or create conversation
        if body.job_id:
            existing = await conn.fetchval(
                """
                SELECT id::text FROM public.conversations
                WHERE applicant_id = $1::uuid AND employer_id = $2::uuid AND job_id = $3::uuid
                """,
                applicant_id, employer_id, body.job_id,
            )
        else:
            existing = await conn.fetchval(
                """
                SELECT id::text FROM public.conversations
                WHERE applicant_id = $1::uuid AND employer_id = $2::uuid AND job_id IS NULL
                """,
                applicant_id, employer_id,
            )

        if existing:
            conv_id = existing
        else:
            conv_id = await conn.fetchval(
                """
                INSERT INTO public.conversations (applicant_id, employer_id, job_id, match_id)
                VALUES ($1::uuid, $2::uuid, $3, $4)
                RETURNING id::text
                """,
                applicant_id, employer_id,
                body.job_id,
                body.match_id,
            )

        # Send initial message if provided
        if body.initial_message and body.initial_message.strip():
            sender_role = "applicant" if role == "applicant" else "employer"
            await conn.execute(
                """
                INSERT INTO public.direct_messages (conversation_id, sender_role, content)
                VALUES ($1::uuid, $2, $3)
                """,
                conv_id, sender_role, body.initial_message.strip(),
            )
            # Update last_message_at and unread counter
            other_unread_col = "applicant_unread" if sender_role == "employer" else "employer_unread"
            await conn.execute(
                f"""
                UPDATE public.conversations
                SET last_message_at = NOW(), {other_unread_col} = {other_unread_col} + 1
                WHERE id = $1::uuid
                """,
                conv_id,
            )
            # Log engagement
            await conn.execute(
                """
                INSERT INTO public.engagement_events
                    (applicant_id, employer_id, job_id, event_type, event_data)
                VALUES ($1::uuid, $2::uuid, $3, 'dm_sent', $4::jsonb)
                """,
                applicant_id, employer_id, body.job_id,
                {"conversation_id": conv_id, "sender_role": sender_role},
            )

        # Fetch summary
        if role == "applicant":
            row = await conn.fetchrow(
                """
                SELECT c.id::text AS conversation_id, e.name AS other_party_name,
                       COALESCE(j.title_normalized, j.title_raw) AS job_title,
                       c.last_message_at::text, c.applicant_unread AS unread_count,
                       COUNT(dm.id) AS message_count
                FROM public.conversations c
                JOIN public.employers e ON e.id = c.employer_id
                LEFT JOIN public.jobs j ON j.id = c.job_id
                LEFT JOIN public.direct_messages dm ON dm.conversation_id = c.id
                WHERE c.id = $1::uuid
                GROUP BY c.id, e.name, j.title_normalized, j.title_raw
                """,
                conv_id,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT c.id::text AS conversation_id,
                       CONCAT(a.first_name, ' ', a.last_name) AS other_party_name,
                       COALESCE(j.title_normalized, j.title_raw) AS job_title,
                       c.last_message_at::text, c.employer_unread AS unread_count,
                       COUNT(dm.id) AS message_count
                FROM public.conversations c
                JOIN public.applicants a ON a.id = c.applicant_id
                LEFT JOIN public.jobs j ON j.id = c.job_id
                LEFT JOIN public.direct_messages dm ON dm.conversation_id = c.id
                WHERE c.id = $1::uuid
                GROUP BY c.id, a.first_name, a.last_name, j.title_normalized, j.title_raw
                """,
                conv_id,
            )

    return ConversationSummary(
        conversation_id=row["conversation_id"],
        other_party_name=(row["other_party_name"] or "").strip() or "Unknown",
        job_title=row["job_title"],
        last_message_at=row["last_message_at"],
        unread_count=int(row["unread_count"] or 0),
        message_count=int(row["message_count"] or 0),
    )


# ---------------------------------------------------------------------------
# GET /conversations/{conversation_id}/messages
# ---------------------------------------------------------------------------

@router.get("/{conversation_id}/messages", response_model=ConversationDetail)
async def get_messages(
    conversation_id: str,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> ConversationDetail:
    async with get_db() as conn:
        role, applicant_id, employer_id = await _resolve_ids(conn, current_user)

        # Verify access
        if role == "applicant":
            conv = await conn.fetchrow(
                """
                SELECT c.id::text, e.name AS other_party_name,
                       COALESCE(j.title_normalized, j.title_raw) AS job_title
                FROM public.conversations c
                JOIN public.employers e ON e.id = c.employer_id
                LEFT JOIN public.jobs j ON j.id = c.job_id
                WHERE c.id = $1::uuid AND c.applicant_id = $2::uuid
                """,
                conversation_id, applicant_id,
            )
        else:
            conv = await conn.fetchrow(
                """
                SELECT c.id::text,
                       CONCAT(a.first_name, ' ', a.last_name) AS other_party_name,
                       COALESCE(j.title_normalized, j.title_raw) AS job_title
                FROM public.conversations c
                JOIN public.applicants a ON a.id = c.applicant_id
                LEFT JOIN public.jobs j ON j.id = c.job_id
                WHERE c.id = $1::uuid AND c.employer_id = $2::uuid
                """,
                conversation_id, employer_id,
            )

        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        msgs = await conn.fetch(
            """
            SELECT id::text AS message_id, sender_role, content, created_at::text
            FROM public.direct_messages
            WHERE conversation_id = $1::uuid
            ORDER BY created_at ASC
            LIMIT $2
            """,
            conversation_id, _MAX_MESSAGES,
        )

        my_role = "applicant" if role == "applicant" else "employer"

    return ConversationDetail(
        conversation_id=conv["id"],
        other_party_name=(conv["other_party_name"] or "").strip() or "Unknown",
        job_title=conv["job_title"],
        messages=[
            DirectMessageOut(
                message_id=m["message_id"],
                sender_role=m["sender_role"],
                content=m["content"],
                created_at=m["created_at"],
                is_mine=(m["sender_role"] == my_role),
            )
            for m in msgs
        ],
    )


# ---------------------------------------------------------------------------
# POST /conversations/{conversation_id}/messages
# ---------------------------------------------------------------------------

@router.post("/{conversation_id}/messages", response_model=DirectMessageOut, status_code=201)
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> DirectMessageOut:
    if not body.content.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")

    async with get_db() as conn:
        role, applicant_id, employer_id = await _resolve_ids(conn, current_user)
        sender_role = "applicant" if role == "applicant" else "employer"

        # Verify access
        if role == "applicant":
            conv = await conn.fetchrow(
                "SELECT id, employer_id FROM public.conversations WHERE id = $1::uuid AND applicant_id = $2::uuid",
                conversation_id, applicant_id,
            )
        else:
            conv = await conn.fetchrow(
                "SELECT id, applicant_id FROM public.conversations WHERE id = $1::uuid AND employer_id = $2::uuid",
                conversation_id, employer_id,
            )

        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        msg_row = await conn.fetchrow(
            """
            INSERT INTO public.direct_messages (conversation_id, sender_role, content)
            VALUES ($1::uuid, $2, $3)
            RETURNING id::text AS message_id, sender_role, content, created_at::text
            """,
            conversation_id, sender_role, body.content.strip(),
        )

        # Update unread counter for the other party
        other_unread_col = "applicant_unread" if sender_role == "employer" else "employer_unread"
        await conn.execute(
            f"""
            UPDATE public.conversations
            SET last_message_at = NOW(), {other_unread_col} = {other_unread_col} + 1
            WHERE id = $1::uuid
            """,
            conversation_id,
        )

        # Tray signal for the recipient. The messages surfaces poll (thread 15s,
        # inbox 60s), but the rest of the app only hears about a new DM through
        # the notification tray. Deduped per conversation inside a 15-minute
        # window so a burst of messages produces one tray item, not ten.
        # Guarded: a notification hiccup must never 500 the send itself.
        try:
            await _notify_dm_recipient(conn, role, applicant_id, employer_id, conv, conversation_id, body.content)
        except Exception as exc:
            logger.warning("DM notification failed for conversation %s: %s", conversation_id, exc)

        # Log engagement event
        conv_applicant_id = applicant_id if role == "applicant" else str(conv["applicant_id"])
        conv_employer_id = employer_id if role != "applicant" else str(conv["employer_id"])
        await conn.execute(
            """
            INSERT INTO public.engagement_events
                (applicant_id, employer_id, event_type, event_data)
            VALUES ($1::uuid, $2::uuid, 'dm_sent', $3::jsonb)
            """,
            conv_applicant_id, conv_employer_id,
            {"conversation_id": conversation_id, "sender_role": sender_role},
        )

    return DirectMessageOut(
        message_id=msg_row["message_id"],
        sender_role=msg_row["sender_role"],
        content=msg_row["content"],
        created_at=msg_row["created_at"],
        is_mine=True,
    )


async def _notify_dm_recipient(
    conn: Any, role: str, applicant_id: str | None, employer_id: str | None,
    conv: Any, conversation_id: str, content: str,
) -> None:
    if role == "applicant":
        recipient = await conn.fetchrow(
            "SELECT ec.user_id, a.first_name, a.last_name FROM public.employer_contacts ec "
            "JOIN public.applicants a ON a.id = $2::uuid "
            "WHERE ec.employer_id = $1::uuid ORDER BY ec.created_at LIMIT 1",
            conv["employer_id"], applicant_id,
        )
        sender_name = (
            f"{recipient['first_name']} {recipient['last_name']}".strip() if recipient else "An applicant"
        )
    else:
        recipient = await conn.fetchrow(
            "SELECT a.user_id, e.name AS employer_name FROM public.applicants a "
            "JOIN public.employers e ON e.id = $2::uuid WHERE a.id = $1::uuid",
            conv["applicant_id"], employer_id,
        )
        sender_name = recipient["employer_name"] if recipient else "An employer"
    if recipient and recipient["user_id"]:
        await notify(
            conn,
            recipient_user_id=str(recipient["user_id"]),
            kind="dm_received",
            title=f"New message from {sender_name or 'your contact'}",
            body=content.strip()[:140],
            link_href=(
                f"/employer/messages/{conversation_id}"
                if role == "applicant"
                else f"/applicant/messages/{conversation_id}"
            ),
            payload={"conversation_id": conversation_id},
            dedupe_key=f"dm:{conversation_id}",
            dedupe_window_minutes=15,
        )


# ---------------------------------------------------------------------------
# POST /conversations/{conversation_id}/read
# ---------------------------------------------------------------------------

@router.post("/{conversation_id}/read", status_code=200)
async def mark_read(
    conversation_id: str,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> dict:
    async with get_db() as conn:
        role, applicant_id, employer_id = await _resolve_ids(conn, current_user)
        my_unread_col = "applicant_unread" if role == "applicant" else "employer_unread"

        if role == "applicant":
            result = await conn.execute(
                f"UPDATE public.conversations SET {my_unread_col} = 0 WHERE id = $1::uuid AND applicant_id = $2::uuid",
                conversation_id, applicant_id,
            )
        else:
            result = await conn.execute(
                f"UPDATE public.conversations SET {my_unread_col} = 0 WHERE id = $1::uuid AND employer_id = $2::uuid",
                conversation_id, employer_id,
            )

        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}
