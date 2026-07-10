"""Credential Engine Registry adapter — the national taxonomy backbone.

Public read API — no key needed. Docs: https://credentialengine.org/registry
The Registry publishes 130,000+ credentials described in CTDL (JSON-LD).

Two operations we use:
  1. `resolve(ctdl_uri)`: fetch the full CTDL record for a URI in our taxonomy
  2. `search(query)`: search by name/keyword for admin taxonomy work

Everything else the Registry offers (competencies, transfer value, occupations)
is out of scope for this MVP but structurally aligned.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from .shared import VerificationResult, VerificationStatus

logger = logging.getLogger(__name__)

# Public reads. Registry Assistant (writes) requires an API key + publisher status.
_BASE = "https://credentialengineregistry.org"
_RESOLVE_PATH = "/resources/{uri_id}"
_SEARCH_PATH = "/assistant/search"
_TIMEOUT = 10.0
_UA = "SkillPointe-Match/0.1"


async def resolve(ctdl_uri: str) -> VerificationResult:
    """Fetch the CTDL record behind a URI in our credential_definitions table.

    Registry URIs look like: https://credentialengineregistry.org/resources/ce-<uuid>
    """
    if not ctdl_uri or "credentialengineregistry.org" not in ctdl_uri:
        return VerificationResult(
            provider="credential_engine",
            status=VerificationStatus.NOT_FOUND,
            raw={"reason": "not_a_ctdl_uri"},
        )

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers={"User-Agent": _UA, "Accept": "application/json"}) as c:
            r = await c.get(ctdl_uri)
        if r.status_code == 404:
            return VerificationResult(
                provider="credential_engine",
                status=VerificationStatus.NOT_FOUND,
                raw={"http_status": 404, "uri": ctdl_uri},
            )
        if r.status_code != 200:
            return VerificationResult(
                provider="credential_engine",
                status=VerificationStatus.ERROR,
                raw={"http_status": r.status_code, "uri": ctdl_uri},
            )
        payload = r.json()
        name = _extract_name(payload)
        return VerificationResult(
            provider="credential_engine",
            status=VerificationStatus.VERIFIED,
            external_ref=ctdl_uri,
            credential=name,
            raw=payload if isinstance(payload, dict) else {"payload": payload},
        )
    except Exception as e:
        logger.warning(f"CTDL resolve failed for {ctdl_uri}: {e}")
        return VerificationResult(
            provider="credential_engine",
            status=VerificationStatus.ERROR,
            raw={"exception": str(e), "uri": ctdl_uri},
        )


async def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Keyword search — admin tool to align a local credential to CTDL."""
    if not query.strip():
        return []
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers={"User-Agent": _UA}) as c:
            r = await c.get(
                f"{_BASE}{_SEARCH_PATH}",
                params={"q": query, "type": "credential", "limit": limit},
            )
        if r.status_code != 200:
            return []
        data = r.json()
        hits = data.get("data") or data.get("results") or []
        return [_normalize_hit(h) for h in hits][:limit]
    except Exception as e:
        logger.warning(f"CTDL search failed for {query!r}: {e}")
        return []


def _extract_name(payload: dict[str, Any]) -> Optional[str]:
    """CTDL records use ceterms:name with a language map."""
    if not isinstance(payload, dict):
        return None
    n = payload.get("ceterms:name") or payload.get("name")
    if isinstance(n, dict):
        return n.get("en-US") or n.get("en") or next(iter(n.values()), None)
    if isinstance(n, str):
        return n
    return None


def _normalize_hit(h: dict[str, Any]) -> dict[str, Any]:
    return {
        "ctdl_uri": h.get("@id") or h.get("ceterms:ctid") or h.get("id"),
        "name":     _extract_name(h),
        "type":     h.get("@type") or h.get("type"),
        "issuer":   _extract_issuer(h),
    }


def _extract_issuer(h: dict[str, Any]) -> Optional[str]:
    org = h.get("ceterms:ownedBy") or h.get("ownedBy") or h.get("issuer")
    if isinstance(org, list) and org:
        org = org[0]
    if isinstance(org, dict):
        return _extract_name(org)
    if isinstance(org, str):
        return org
    return None
