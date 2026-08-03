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

from datetime import datetime
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
    dedupe_key: Optional[str] = None,
    dedupe_window_minutes: int = 10,
    deliver_after: Optional[datetime] = None,
) -> None:
    """Write a notification row (which will be picked up by future workers).

    ``dedupe_key`` identifies the entity the notification is about (e.g. an
    application or slot id). When set, a second notification with the same
    (kind, recipient, dedupe_key) inside ``dedupe_window_minutes`` is silently
    skipped — retries and double-fired events don't spam the tray.

    ``deliver_after`` defers visibility: the row exists immediately but the
    recipient-facing readers (tray API, future email/SMS workers) skip it
    until the timestamp passes. Deleting the row before then cancels delivery
    entirely — this is the quiet window behind revertable decisions.
    """
    payload = dict(payload or {})
    if dedupe_key:
        payload["_dedupe"] = dedupe_key
        exists = await conn.fetchval(
            """
            SELECT 1 FROM public.notifications
            WHERE kind::text = $1
              AND recipient_user_id IS NOT DISTINCT FROM $2::uuid
              AND recipient_role IS NOT DISTINCT FROM $3
              AND payload->>'_dedupe' = $4
              AND created_at > NOW() - make_interval(mins => $5)
            LIMIT 1
            """,
            kind, recipient_user_id, recipient_role, dedupe_key, dedupe_window_minutes,
        )
        if exists:
            return

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
        # Best-effort phone lookup from the applicant row. (employer_contacts
        # has no phone column — the old UNION against it made every notify()
        # fail with UndefinedColumnError, 500ing the calling endpoint.)
        phone_row = await conn.fetchrow(
            "SELECT phone FROM public.applicants WHERE user_id = $1 LIMIT 1",
            recipient_user_id,
        )
        if phone_row:
            phone = phone_row["phone"]

    await conn.execute(
        """
        INSERT INTO public.notifications
          (recipient_user_id, recipient_role, kind, title, body, link_href, payload,
           email_pending, sms_pending, phone, deliver_after)
        VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb, $8, $9, $10, $11)
        """,
        recipient_user_id,
        recipient_role,
        kind,
        title,
        body,
        link_href,
        _to_jsonb(payload),
        email_opt_in,
        bool(sms_opt_in and phone),
        phone,
        deliver_after,
    )


def _to_jsonb(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize the payload to a JSON-safe dict (UUIDs/datetimes → strings).

    The pooled connections register a jsonb codec whose ENCODER is json.dumps
    (see app/db.py), so the value passed to the driver must be the dict itself.
    Passing a pre-dumped string here double-encodes: the payload lands in
    Postgres as a jsonb *string* instead of an object, which silently broke
    payload->>'…' consumers (including the notify dedupe check).
    """
    import json
    return json.loads(json.dumps(payload, default=str))
