"""
Transactional outbox writer.

`write_event` inserts into event_outbox using the SAME asyncpg connection as the
caller's domain mutation, so the event is committed atomically with the state
change. Never raises on a missing table / duplicate id in a way that would roll
back the business write — emission is best-effort relative to the core write,
but when the table exists it participates in the transaction.
"""
from __future__ import annotations

import logging
from typing import Any

import asyncpg

from app.skilled_pro import events

logger = logging.getLogger(__name__)


async def write_event(
    conn: asyncpg.Connection,
    aggregate_type: str,
    aggregate_id: str | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> str | None:
    """Append a domain event to the outbox. Returns the event_id (or None on skip)."""
    ev = events.make_event(aggregate_type, aggregate_id, event_type, payload)
    try:
        await conn.execute(
            """
            INSERT INTO public.event_outbox
                (event_id, aggregate_type, aggregate_id, event_type, payload, source)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (event_id) DO NOTHING
            """,
            ev["event_id"], ev["aggregate_type"],
            ev["aggregate_id"], ev["event_type"], ev["payload"], ev["source"],
        )
        return ev["event_id"]
    except asyncpg.UndefinedTableError:
        # Sync not migrated in this environment — degrade quietly.
        logger.debug("event_outbox missing; skipping emission for %s", event_type)
        return None
