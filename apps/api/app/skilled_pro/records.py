"""
Shared writers for the append-only, signed, hash-chained audit ledgers
(credential_records, consent_records).

Centralized so every path that mutates a credential or consent setting —
self-service routers AND bulk ingestion — produces a consistent, tamper-evident
record. Each record's signature covers its position in the per-subject chain.
"""
from __future__ import annotations

from typing import Any

import asyncpg

from app.skilled_pro import keyring, signing
from app.skilled_pro.outbox import write_event
from app.skilled_pro.signing import GENESIS_HASH


async def append_credential_record(
    conn: asyncpg.Connection,
    applicant_id: str,
    credential_id: str | None,
    event: str,
    payload: dict[str, Any],
) -> None:
    prev = await conn.fetchrow(
        "SELECT chain_hash FROM public.credential_records "
        "WHERE applicant_id = $1 ORDER BY created_at DESC LIMIT 1",
        applicant_id,
    )
    prev_hash = prev["chain_hash"] if prev else GENESIS_HASH
    signed = signing.sign_record(payload, keyring.get_private_key(), prev_hash=prev_hash)
    await conn.execute(
        """
        INSERT INTO public.credential_records
            (credential_id, applicant_id, event, payload, content_hash,
             prev_hash, chain_hash, signature, algorithm, signing_key_id)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
        """,
        credential_id, applicant_id, event, payload, signed.content_hash,
        signed.prev_hash, signed.chain_hash, signed.signature, signed.algorithm,
        keyring.get_key_id(),
    )
    # Transactional outbox: emit a sync event on the same connection.
    await write_event(
        conn, "credential", applicant_id, f"credential.{event}",
        {"credential_id": credential_id, "event": event},
    )


async def append_consent_record(
    conn: asyncpg.Connection,
    applicant_id: str,
    data_category: str,
    payload: dict[str, Any],
    *,
    scope: str = "external_sharing",
    action: str = "set",
    requester_category: str | None = None,
) -> None:
    prev = await conn.fetchrow(
        "SELECT chain_hash FROM public.consent_records "
        "WHERE applicant_id = $1 ORDER BY created_at DESC LIMIT 1",
        applicant_id,
    )
    prev_hash = prev["chain_hash"] if prev else GENESIS_HASH
    signed = signing.sign_record(payload, keyring.get_private_key(), prev_hash=prev_hash)
    await conn.execute(
        """
        INSERT INTO public.consent_records
            (applicant_id, data_category, scope, action, requester_category,
             payload, content_hash, prev_hash, chain_hash, signature)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
        """,
        applicant_id, data_category, scope, action, requester_category,
        payload, signed.content_hash, signed.prev_hash, signed.chain_hash, signed.signature,
    )
    # Transactional outbox: emit a sync event on the same connection.
    await write_event(
        conn, "consent", applicant_id, "consent.updated",
        {"data_category": data_category, "scope": scope, "action": action,
         "requester_category": requester_category},
    )
