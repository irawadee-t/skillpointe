"""
Universal in-app notification tray for the current user.

GET  /me/notifications                  — list (recent first)
POST /me/notifications/{id}/read
POST /me/notifications/read-all
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.db import get_db

router = APIRouter(prefix="/me/notifications", tags=["me"])


class Notification(BaseModel):
    id: UUID
    kind: str
    title: str
    body: Optional[str] = None
    link_href: Optional[str] = None
    read: bool
    created_at: str
    payload: dict = {}


class NotificationSummary(BaseModel):
    unread: int
    items: list[Notification]
    total: int = 0
    limit: int = 30
    offset: int = 0


@router.get("", response_model=NotificationSummary)
async def list_notifications(
    limit: int = 30,
    offset: int = 0,
    only_unread: bool = False,
    user: CurrentUser = Depends(get_current_user),
):
    role = user.role
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    async with get_db() as conn:
        where = [
            "(recipient_user_id = $1 OR recipient_role = $2)",
            # Deferred rows (deliver_after in the future) are invisible until
            # their quiet window passes — see notify(deliver_after=...).
            "(deliver_after IS NULL OR deliver_after <= NOW())",
        ]
        params: list = [user.user_id, role]
        if only_unread:
            where.append("read_at IS NULL")
        rows = await conn.fetch(
            f"""
            SELECT id, kind::text AS kind, title, body, link_href, payload,
                   read_at IS NOT NULL AS read, created_at,
                   count(*) OVER () AS _total
              FROM public.notifications
             WHERE {" AND ".join(where)}
          ORDER BY created_at DESC
             LIMIT {int(limit)} OFFSET {int(offset)}
            """,
            *params,
        )
        unread = await conn.fetchval(
            "SELECT count(*) FROM public.notifications WHERE (recipient_user_id = $1 OR recipient_role = $2) AND read_at IS NULL AND (deliver_after IS NULL OR deliver_after <= NOW())",
            user.user_id, role,
        )
    items = [
        Notification(
            id=r["id"], kind=r["kind"], title=r["title"], body=r["body"],
            link_href=r["link_href"], read=r["read"],
            created_at=r["created_at"].isoformat(),
            payload=r["payload"] if isinstance(r["payload"], dict) else {},
        )
        for r in rows
    ]
    total = int(rows[0]["_total"]) if rows else 0
    return NotificationSummary(unread=int(unread or 0), items=items,
                               total=total, limit=limit, offset=offset)


@router.post("/{notif_id}/read")
async def mark_read(notif_id: UUID, user: CurrentUser = Depends(get_current_user)):
    async with get_db() as conn:
        await conn.execute(
            "UPDATE public.notifications SET read_at = NOW() WHERE id = $1 AND (recipient_user_id = $2 OR recipient_role = $3) AND read_at IS NULL",
            notif_id, user.user_id, user.role,
        )
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(user: CurrentUser = Depends(get_current_user)):
    async with get_db() as conn:
        await conn.execute(
            "UPDATE public.notifications SET read_at = NOW() WHERE (recipient_user_id = $1 OR recipient_role = $2) AND read_at IS NULL",
            user.user_id, user.role,
        )
    return {"ok": True}
