"""
Central audit-trail helper — one place that knows the real `audit_logs` schema
so every privileged/sensitive action records who did what, consistently.

Schema (public.audit_logs):
    actor_id uuid, actor_role text, action text NOT NULL,
    entity_type text, entity_id uuid, before_state jsonb, after_state jsonb,
    metadata jsonb, ip_address text, created_at timestamptz

Never let an audit write fail the caller's business transaction silently — but
DO surface it: the caller passes its open connection so the audit row is part of
the same transaction when there is one (tamper-evident consistency).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def write_audit(
    conn,
    *,
    action: str,
    actor_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Insert one audit row using the caller's connection (same txn when present)."""
    await conn.execute(
        """
        INSERT INTO public.audit_logs
          (actor_id, actor_role, action, entity_type, entity_id,
           before_state, after_state, metadata, ip_address)
        VALUES ($1::uuid, $2, $3, $4, $5::uuid, $6::jsonb, $7::jsonb, $8::jsonb, $9)
        """,
        actor_id,
        actor_role,
        action,
        entity_type,
        entity_id,
        json.dumps(before) if before is not None else None,
        json.dumps(after) if after is not None else None,
        json.dumps(metadata) if metadata is not None else None,
        ip_address,
    )
