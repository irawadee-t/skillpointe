"""
SKILLED Nation <-> Pro sync console (admin).

Operate and observe the event pipeline: status, relay (publish), peer consume,
and reconciliation. Includes a synthetic event emitter for demos/QA.
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser, require_admin
from app.db import get_db
from app.skilled_pro import events, stream

router = APIRouter(prefix="/admin/sync", tags=["sync"])


# Human-readable partner names for the admin UI. Fall back to the raw source
# tag (title-cased) for any partner not in this map.
PARTNER_LABELS = {
    events.THIS_SOURCE: "SKILLED Pro",
    events.PEER_SOURCE: "SKILLED Nation",
}


class RecentEvent(BaseModel):
    event_id: str
    aggregate_type: str
    event_type: str
    source: str
    occurred_at: str
    published: bool


class SyncStatus(BaseModel):
    outbox_unpublished: int
    outbox_total: int
    inbox_total: int
    stream_depth: int
    pending: int
    in_sync: bool
    recent: list[RecentEvent]


class PartnerHealth(BaseModel):
    source: str                       # raw tag, e.g. "skilled_pro"
    name: str                         # display name, e.g. "SKILLED Pro"
    status: str                       # "healthy" | "delayed" | "down"
    last_sync_at: Optional[str]       # ISO8601 of most recent successful relay
    events_24h: int                   # events successfully relayed in last 24h
    backlog: int                      # events awaiting relay for this partner
    oldest_pending_at: Optional[str]  # ISO8601 of the oldest unpublished event


class StuckEvent(BaseModel):
    event_id: str
    partner: str                      # display name
    source: str
    event_type: str
    aggregate_type: str
    occurred_at: str
    waiting_seconds: int


class PartnerHealthResponse(BaseModel):
    partners: list[PartnerHealth]
    stuck: list[StuckEvent]
    total_backlog: int
    total_events_24h: int


class EmitRequest(BaseModel):
    event_type: str = "credential.verified"
    source: str = events.THIS_SOURCE       # set to "skilled_nation" to test the echo guard
    count: int = 1


@router.get("/status", response_model=SyncStatus)
async def sync_status(user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        st = await stream.status(conn)
        rec = await stream.reconcile(conn)
        rows = await conn.fetch(
            "SELECT event_id, aggregate_type, event_type, source, occurred_at, "
            "published_at FROM public.event_outbox ORDER BY occurred_at DESC LIMIT 12"
        )
    return SyncStatus(
        **st,
        in_sync=rec["in_sync"],
        recent=[
            RecentEvent(
                event_id=r["event_id"], aggregate_type=r["aggregate_type"],
                event_type=r["event_type"], source=r["source"],
                occurred_at=r["occurred_at"].isoformat(),
                published=r["published_at"] is not None,
            )
            for r in rows
        ],
    )


@router.post("/publish")
async def publish(user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        return await stream.publish_unpublished(conn)


@router.post("/consume")
async def consume(user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        return await stream.consume(conn)


@router.post("/reconcile")
async def reconcile(user: Annotated[CurrentUser, Depends(require_admin)]):
    async with get_db() as conn:
        return await stream.reconcile(conn)


@router.get("/partners", response_model=PartnerHealthResponse)
async def partner_health(user: Annotated[CurrentUser, Depends(require_admin)]):
    """
    Per-partner sync health summary for the admin UI. Aggregates the outbox
    grouped by `source` into one row per partner: last successful relay,
    24h throughput, current backlog. Also returns the stuck-event list
    (unpublished > 5 minutes) so admins can retry from one place.
    """
    async with get_db() as conn:
        # Aggregate one row per partner (source). LEFT JOIN so partners with
        # zero events still appear.
        rows = await conn.fetch(
            """
            SELECT
                source,
                COUNT(*) FILTER (WHERE published_at IS NOT NULL) AS relayed_total,
                COUNT(*) FILTER (WHERE published_at IS NULL) AS backlog,
                COUNT(*) FILTER (
                    WHERE published_at IS NOT NULL
                      AND published_at > now() - interval '24 hours'
                ) AS events_24h,
                MAX(published_at) AS last_sync_at,
                MIN(occurred_at) FILTER (WHERE published_at IS NULL) AS oldest_pending_at
            FROM public.event_outbox
            GROUP BY source
            ORDER BY source
            """
        )

        stuck_rows = await conn.fetch(
            """
            SELECT event_id, source, event_type, aggregate_type, occurred_at
            FROM public.event_outbox
            WHERE published_at IS NULL
              AND occurred_at < now() - interval '5 minutes'
            ORDER BY occurred_at ASC
            LIMIT 50
            """
        )

    def _name(src: str) -> str:
        return PARTNER_LABELS.get(src, src.replace("_", " ").title())

    # Silence is NOT health. A partner with no relay activity for QUIET_DAYS
    # gets its own state ("quiet") — an integration that went dark looks
    # exactly like a healthy idle one unless we distinguish them.
    QUIET_DAYS = 3

    def _classify(backlog: int, last_sync: Any, oldest_pending: Any) -> str:
        # Down: real drift — backlog exists and oldest pending is > 1h old.
        # Delayed: some backlog OR pending events aging past 5 minutes.
        # Quiet: nothing pending, but no successful relay in QUIET_DAYS
        #        (or none ever) — needs a look, not a green light.
        # Healthy: no backlog AND a recent successful relay.
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        if oldest_pending is not None:
            age = (now - oldest_pending).total_seconds()
            if age > 3600:
                return "down"
            if age > 300:
                return "delayed"
        if backlog > 100:
            return "down"
        if backlog > 0:
            return "delayed"
        if last_sync is None or (now - last_sync) > timedelta(days=QUIET_DAYS):
            return "quiet"
        return "healthy"

    partners: list[PartnerHealth] = []
    total_backlog = 0
    total_events_24h = 0
    for r in rows:
        source = r["source"]
        backlog = int(r["backlog"] or 0)
        events_24h = int(r["events_24h"] or 0)
        last_sync = r["last_sync_at"]
        oldest_pending = r["oldest_pending_at"]
        total_backlog += backlog
        total_events_24h += events_24h
        partners.append(PartnerHealth(
            source=source,
            name=_name(source),
            status=_classify(backlog, last_sync, oldest_pending),
            last_sync_at=last_sync.isoformat() if last_sync else None,
            events_24h=events_24h,
            backlog=backlog,
            oldest_pending_at=oldest_pending.isoformat() if oldest_pending else None,
        ))

    # Ensure both known partners appear even with no history yet.
    seen = {p.source for p in partners}
    for src in (events.THIS_SOURCE, events.PEER_SOURCE):
        if src not in seen:
            partners.append(PartnerHealth(
                # Never-synced is "quiet", not "healthy" — no evidence either way.
                source=src, name=_name(src), status="quiet",
                last_sync_at=None, events_24h=0, backlog=0, oldest_pending_at=None,
            ))

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    stuck = [
        StuckEvent(
            event_id=r["event_id"],
            partner=_name(r["source"]),
            source=r["source"],
            event_type=r["event_type"],
            aggregate_type=r["aggregate_type"],
            occurred_at=r["occurred_at"].isoformat(),
            waiting_seconds=int((now - r["occurred_at"]).total_seconds()),
        )
        for r in stuck_rows
    ]

    return PartnerHealthResponse(
        partners=partners,
        stuck=stuck,
        total_backlog=total_backlog,
        total_events_24h=total_events_24h,
    )


@router.post("/emit")
async def emit(body: EmitRequest, user: Annotated[CurrentUser, Depends(require_admin)]):
    """Emit synthetic event(s) into the outbox (demo / QA harness)."""
    emitted: list[Optional[str]] = []
    async with get_db() as conn:
        for i in range(max(1, min(body.count, 50))):
            ev = events.make_event(
                "demo", None, body.event_type,
                {"demo": True, "n": i}, source=body.source,
            )
            # Honor a caller-specified source (e.g. to exercise the echo guard).
            await conn.execute(
                "INSERT INTO public.event_outbox "
                "(event_id, aggregate_type, aggregate_id, event_type, payload, source) "
                "VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING",
                ev["event_id"], ev["aggregate_type"], None, ev["event_type"],
                ev["payload"], ev["source"],
            )
            emitted.append(ev["event_id"])
    return {"emitted": len(emitted), "event_ids": emitted}
