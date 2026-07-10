"""
Notification dispatcher — email and SMS.

Both are STUBBED: this module writes rows to public.notifications with
`email_pending=true` / `sms_pending=true`. A future worker will pick these up
and hit Resend / Twilio (or similar) and flip the *_sent_at columns.

The `notify` helper decides which channels apply based on the recipient's
`user_profiles.email_opt_in` and `sms_opt_in` flags. In-app notifications
are always created (the row itself is the in-app payload).
"""
from __future__ import annotations

from typing import Any, Optional

import asyncpg


async def notify(
    conn: asyncpg.Connection,
    *,
    recipient_user_id: Optional[str] = None,
    recipient_role: Optional[str] = None,      # 'admin' etc.; group notify
    kind: str,
    title: str,
    body: Optional[str] = None,
    link_href: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    """Write a notification row (which will be picked up by future workers)."""
    email_opt_in = True
    sms_opt_in = False
    phone: Optional[str] = None

    if recipient_user_id:
        prefs = await conn.fetchrow(
            "SELECT email_opt_in, sms_opt_in FROM public.user_profiles WHERE user_id = $1",
            recipient_user_id,
        )
        if prefs:
            email_opt_in = bool(prefs["email_opt_in"])
            sms_opt_in = bool(prefs["sms_opt_in"])
        # Best-effort phone lookup from either applicant or employer contact row.
        phone_row = await conn.fetchrow(
            """
            SELECT phone FROM public.applicants WHERE user_id = $1
            UNION ALL
            SELECT phone FROM public.employer_contacts WHERE user_id = $1
            LIMIT 1
            """,
            recipient_user_id,
        )
        if phone_row:
            phone = phone_row["phone"]

    await conn.execute(
        """
        INSERT INTO public.notifications
          (recipient_user_id, recipient_role, kind, title, body, link_href, payload,
           email_pending, sms_pending, phone)
        VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb, $8, $9, $10)
        """,
        recipient_user_id,
        recipient_role,
        kind,
        title,
        body,
        link_href,
        _to_jsonb(payload or {}),
        email_opt_in,
        bool(sms_opt_in and phone),
        phone,
    )


def _to_jsonb(payload: dict[str, Any]) -> str:
    import json
    return json.dumps(payload, default=str)
