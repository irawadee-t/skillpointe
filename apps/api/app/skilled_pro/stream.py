"""
Redis Streams transport for SKILLED Nation <-> Pro sync.

- publish_unpublished: relay outbox -> Redis Stream (XADD), mark published.
- consume: peer consumer group reads (XREADGROUP), applies idempotently into
  sync_inbox, ACKs (XACK). Origin-tagged echoes are skipped, duplicates are
  no-ops (ON CONFLICT DO NOTHING).
- reconcile: diff published events vs. applied inbox events.
- status: stream depth + consumer-group pending.

Idempotency is enforced twice: the consumer group won't re-deliver ACKed
messages, and sync_inbox.event_id is UNIQUE — so even a redelivery is a no-op.
"""
from __future__ import annotations

import logging
from typing import Any

import asyncpg

from app.config import get_settings
from app.skilled_pro import events

logger = logging.getLogger(__name__)

STREAM = "skilled.events"
GROUP = "skilled_nation"
CONSUMER = "nation-1"
# This consumer acts AS the SKILLED Nation peer, so it skips events that the peer
# itself originated (echoes) and applies events from SKILLED Pro.
CONSUMER_SOURCE = events.PEER_SOURCE


def _redis():
    import redis.asyncio as aioredis
    return aioredis.from_url(get_settings().redis_url, decode_responses=True)


async def publish_unpublished(conn: asyncpg.Connection, batch: int = 500) -> dict[str, int]:
    rows = await conn.fetch(
        "SELECT event_id, aggregate_type, aggregate_id::text AS aggregate_id, "
        "event_type, payload, source FROM public.event_outbox "
        "WHERE published_at IS NULL ORDER BY occurred_at ASC LIMIT $1",
        batch,
    )
    if not rows:
        return {"published": 0}

    r = _redis()
    published = 0
    try:
        for row in rows:
            ev = {
                "event_id": row["event_id"],
                "aggregate_type": row["aggregate_type"],
                "aggregate_id": row["aggregate_id"],
                "event_type": row["event_type"],
                "payload": row["payload"],          # jsonb codec already decoded to dict
                "source": row["source"],
            }
            await r.xadd(STREAM, {"data": events.canonical_json(ev)})
            await conn.execute(
                "UPDATE public.event_outbox SET published_at = now() WHERE event_id = $1",
                row["event_id"],
            )
            published += 1
    finally:
        await r.aclose()
    return {"published": published}


async def _ensure_group(r) -> None:
    try:
        await r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception as exc:  # BUSYGROUP if it already exists
        if "BUSYGROUP" not in str(exc):
            raise


async def consume(conn: asyncpg.Connection, count: int = 200) -> dict[str, int]:
    r = _redis()
    applied = duplicates = skipped = consumed = 0
    try:
        await _ensure_group(r)
        resp = await r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=count, block=200)
        for _stream, messages in resp or []:
            for msg_id, fields in messages:
                consumed += 1
                ev = events.parse_event(fields["data"])
                if not events.should_consume(ev, CONSUMER_SOURCE):
                    skipped += 1
                    await r.xack(STREAM, GROUP, msg_id)
                    continue
                payload = ev.get("payload")
                if not isinstance(payload, dict):
                    payload = events.parse_event(payload) if payload else {}
                # Pass the dict directly — the asyncpg jsonb codec encodes it
                # (a pre-serialized string + ::jsonb would double-encode).
                status = await conn.execute(
                    """
                    INSERT INTO public.sync_inbox
                        (event_id, aggregate_type, aggregate_id, event_type, payload, source)
                    VALUES ($1,$2,$3,$4,$5,$6)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    ev["event_id"], ev["aggregate_type"], ev.get("aggregate_id"),
                    ev["event_type"], payload, ev.get("source") or "unknown",
                )
                if status.endswith("1"):
                    applied += 1
                else:
                    duplicates += 1
                await r.xack(STREAM, GROUP, msg_id)
    finally:
        await r.aclose()
    return {"consumed": consumed, "applied": applied, "duplicates": duplicates, "skipped": skipped}


async def reconcile(conn: asyncpg.Connection) -> dict[str, Any]:
    # Only events the peer is expected to apply count toward drift — i.e. published
    # events that did NOT originate from the peer itself (those are echoes it skips).
    pub = await conn.fetch(
        "SELECT event_id FROM public.event_outbox "
        "WHERE published_at IS NOT NULL AND source <> $1",
        CONSUMER_SOURCE,
    )
    inb = await conn.fetch("SELECT event_id FROM public.sync_inbox")
    drift = events.compute_drift([r["event_id"] for r in pub], [r["event_id"] for r in inb])
    return {
        "published": len(pub),
        "applied": len(inb),
        "missing_in_inbox": drift["missing_in_inbox"],
        "extra_in_inbox": drift["extra_in_inbox"],
        "in_sync": len(drift["missing_in_inbox"]) == 0,
    }


async def status(conn: asyncpg.Connection) -> dict[str, Any]:
    unpublished = await conn.fetchval(
        "SELECT count(*) FROM public.event_outbox WHERE published_at IS NULL"
    )
    outbox_total = await conn.fetchval("SELECT count(*) FROM public.event_outbox")
    inbox_total = await conn.fetchval("SELECT count(*) FROM public.sync_inbox")

    stream_len = pending = 0
    r = _redis()
    try:
        stream_len = await r.xlen(STREAM)
        try:
            await _ensure_group(r)
            info = await r.xpending(STREAM, GROUP)
            pending = info["pending"] if isinstance(info, dict) else (info[0] if info else 0)
        except Exception:
            pending = 0
    except Exception as exc:
        logger.warning("Redis status unavailable: %s", exc)
    finally:
        await r.aclose()

    return {
        "outbox_unpublished": int(unpublished or 0),
        "outbox_total": int(outbox_total or 0),
        "inbox_total": int(inbox_total or 0),
        "stream_depth": int(stream_len or 0),
        "pending": int(pending or 0),
    }
