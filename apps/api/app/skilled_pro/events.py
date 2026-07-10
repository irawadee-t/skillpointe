"""
Domain event model for SKILLED Nation <-> Pro sync.

Pure: envelope construction, canonical serialization, the origin-tag echo guard,
and the reconciliation diff. No I/O — unit-tested. The DB outbox/inbox and the
Redis Stream transport live in outbox.py / stream.py.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Iterable

# This service's identity. Events we emit are tagged with it; events we receive
# already tagged with it are echoes and must NOT be re-applied.
THIS_SOURCE = "skilled_pro"
PEER_SOURCE = "skilled_nation"

# Domain event types worth syncing across the two products.
EVENT_CREDENTIAL_VERIFIED = "credential.verified"
EVENT_CREDENTIAL_UPDATED = "credential.updated"
EVENT_CONSENT_UPDATED = "consent.updated"
EVENT_PROFILE_SUMMARY = "profile.summary_updated"


def new_event_id() -> str:
    return uuid.uuid4().hex


def make_event(
    aggregate_type: str,
    aggregate_id: str | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    source: str = THIS_SOURCE,
    event_id: str | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id or new_event_id(),
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "event_type": event_type,
        "payload": payload or {},
        "source": source,
    }


def canonical_json(event: dict[str, Any]) -> str:
    """Stable serialization for the stream payload (sorted keys, compact)."""
    return json.dumps(event, sort_keys=True, separators=(",", ":"), default=str)


def parse_event(raw: str | dict[str, Any]) -> dict[str, Any]:
    return raw if isinstance(raw, dict) else json.loads(raw)


def should_consume(event: dict[str, Any], my_source: str = THIS_SOURCE) -> bool:
    """
    Echo guard: never re-apply an event that originated here. An event with no
    source is treated as foreign (safe to consume).
    """
    return event.get("source") != my_source


def compute_drift(
    published_ids: Iterable[str],
    inbox_ids: Iterable[str],
) -> dict[str, list[str]]:
    """
    Reconciliation diff between what was published and what the peer applied.
    `missing_in_inbox` = published but never applied (real drift to alert on).
    `extra_in_inbox`   = applied but not in our published set (foreign-origin, fine).
    """
    pub = set(published_ids)
    inb = set(inbox_ids)
    return {
        "missing_in_inbox": sorted(pub - inb),
        "extra_in_inbox": sorted(inb - pub),
    }
