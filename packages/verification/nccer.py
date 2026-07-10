"""NCCER Verify adapter — National Registry of Craft Professionals.

NCCER's Registry is the largest US registry of trades workers (~500K+ craft
professionals). Every certified worker has an NCCER Card Number and their
completions are permanent, transferable, and verifiable.

The Verify API is partnership-gated (contact partners@nccer.org). When we don't
have credentials configured, this adapter returns a `stubbed=True` result that
is well-formed but must not be surfaced as "verified" in user-facing UI.

Real endpoint shape (approximate, based on NCCER Registry docs):
  GET  /api/v1/registry/verify?card={num}&last_name={ln}
    → { "card_number", "name", "modules": [ { "code", "title", "completed_on" } ], "status" }
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from .shared import VerificationResult, VerificationStatus

logger = logging.getLogger(__name__)

_BASE = os.environ.get("NCCER_API_BASE", "https://api.nccer.org")
_TIMEOUT = 8.0


async def verify_card(
    card_number: str,
    last_name: str,
    *,
    api_key: str = "",
    canonical_code: str = "",
) -> VerificationResult:
    """Look up an NCCER card # + last name against the National Registry."""
    card_number = (card_number or "").strip()
    last_name = (last_name or "").strip()
    if not card_number:
        return VerificationResult(
            provider="nccer",
            status=VerificationStatus.NOT_FOUND,
            raw={"reason": "no_card_number"},
        )

    if not api_key:
        return _stub(card_number, last_name, canonical_code)

    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": "SkillPointe-Match/0.1",
            },
        ) as c:
            r = await c.get(
                f"{_BASE}/api/v1/registry/verify",
                params={"card": card_number, "last_name": last_name},
            )
        if r.status_code == 404:
            return VerificationResult(
                provider="nccer",
                status=VerificationStatus.NOT_FOUND,
                external_ref=card_number,
                raw={"http_status": 404},
            )
        if r.status_code == 401 or r.status_code == 403:
            return VerificationResult(
                provider="nccer",
                status=VerificationStatus.ERROR,
                raw={"reason": "unauthorized", "http_status": r.status_code},
            )
        if r.status_code != 200:
            return VerificationResult(
                provider="nccer",
                status=VerificationStatus.ERROR,
                raw={"http_status": r.status_code, "body": r.text[:400]},
            )
        payload = r.json()
        status = _map_status(payload.get("status", "active"))
        return VerificationResult(
            provider="nccer",
            status=status,
            external_ref=card_number,
            verified_name=payload.get("name"),
            credential=_module_summary(payload.get("modules", []), canonical_code),
            raw=payload,
        )
    except Exception as e:
        logger.warning(f"NCCER verify failed for card {card_number}: {e}")
        return VerificationResult(
            provider="nccer",
            status=VerificationStatus.ERROR,
            raw={"exception": str(e)},
        )


# ---------------------------------------------------------------------------
def _map_status(s: str) -> VerificationStatus:
    s = (s or "").lower()
    if s in ("active", "current", "verified"): return VerificationStatus.VERIFIED
    if s in ("expired",):                       return VerificationStatus.EXPIRED
    if s in ("revoked", "suspended"):           return VerificationStatus.REVOKED
    return VerificationStatus.NOT_FOUND


def _module_summary(modules: list, canonical_code: str = "") -> Optional[str]:
    if not modules:
        return None
    # If the caller told us which credential we're verifying, prefer a match.
    if canonical_code:
        target = canonical_code.replace("nccer_", "").replace("_", " ").lower()
        for m in modules:
            title = (m.get("title") or "").lower()
            if target in title:
                return m.get("title")
    # Otherwise return the most recent module title.
    return modules[0].get("title")


def _stub(card_number: str, last_name: str, canonical_code: str) -> VerificationResult:
    """Deterministic stub — same input always yields same result.

    Uses the last digit of the card number to fan out into different states so
    the UI can be exercised: 0-6 verified, 7 expired, 8 revoked, 9 not-found.
    """
    tail = (card_number[-1] if card_number and card_number[-1].isdigit() else "0")
    if tail == "9":
        return VerificationResult(
            provider="nccer",
            status=VerificationStatus.NOT_FOUND,
            external_ref=card_number,
            stubbed=True,
            raw={"note": "NCCER partner key not configured — this is a stubbed result."},
        )
    if tail == "8":
        status, note = VerificationStatus.REVOKED, "Stub: NCCER card revoked."
    elif tail == "7":
        status, note = VerificationStatus.EXPIRED, "Stub: NCCER card expired."
    else:
        status, note = VerificationStatus.VERIFIED, "Stub: NCCER partner key not configured."

    return VerificationResult(
        provider="nccer",
        status=status,
        external_ref=card_number,
        verified_name=(last_name.title() if last_name else None),
        credential=_stub_module_for_code(canonical_code),
        stubbed=True,
        raw={"note": note, "would_call": f"{_BASE}/api/v1/registry/verify"},
    )


def _stub_module_for_code(code: str) -> str:
    m = {
        "nccer_core":             "NCCER Core Curriculum",
        "nccer_electrical":       "NCCER Electrical Craft Levels 1-4",
        "nccer_welding":          "NCCER Welding Craft Levels 1-3",
        "nccer_hvac":             "NCCER HVAC-R Craft Levels 1-3",
        "nccer_pipefitting":      "NCCER Pipefitting Craft Levels 1-3",
        "nccer_industrial_maint": "NCCER Industrial Maintenance",
    }
    return m.get(code, "NCCER Craft Credential")
