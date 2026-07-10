"""National Student Clearinghouse DegreeVerify adapter.

The NSC covers ~97% of US postsecondary enrollment. DegreeVerify confirms
degree completion, major, and dates. Partnership-gated — see
studentclearinghouse.org/employers/degreeverify. When we don't have the
NSC service account configured, we return a `stubbed=True` result.

Real DegreeVerify API is a SOAP or REST-JSON service depending on your NSC
integration tier. This adapter targets the REST-JSON tier (post-2023 rollout):
  POST /degreeverify/v1/verify
    body: { "first_name", "last_name", "dob", "school_code" }
    → { "verifications": [ { "degree", "conferred_date", "major", "school" } ] }
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from .shared import VerificationResult, VerificationStatus

logger = logging.getLogger(__name__)

_BASE = os.environ.get("NSC_API_BASE", "https://api.studentclearinghouse.org")
_TIMEOUT = 12.0


async def verify_degree(
    first_name: str,
    last_name: str,
    date_of_birth: str,
    *,
    school_code: str = "",
    expected_degree: str = "",
    api_key: str = "",
) -> VerificationResult:
    """Confirm a degree with NSC DegreeVerify."""
    if not (first_name and last_name and date_of_birth):
        return VerificationResult(
            provider="nsc",
            status=VerificationStatus.NOT_FOUND,
            raw={"reason": "missing_identity_fields"},
        )

    if not api_key:
        return _stub(first_name, last_name, expected_degree)

    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "SkillPointe-Match/0.1",
            },
        ) as c:
            r = await c.post(
                f"{_BASE}/degreeverify/v1/verify",
                json={
                    "first_name": first_name,
                    "last_name":  last_name,
                    "dob":        date_of_birth,
                    "school_code": school_code or None,
                },
            )
        if r.status_code == 404:
            return VerificationResult(
                provider="nsc",
                status=VerificationStatus.NOT_FOUND,
                raw={"http_status": 404},
            )
        if r.status_code in (401, 403):
            return VerificationResult(
                provider="nsc",
                status=VerificationStatus.ERROR,
                raw={"reason": "unauthorized", "http_status": r.status_code},
            )
        if r.status_code != 200:
            return VerificationResult(
                provider="nsc",
                status=VerificationStatus.ERROR,
                raw={"http_status": r.status_code, "body": r.text[:400]},
            )
        payload = r.json()
        verifications = payload.get("verifications", [])
        if not verifications:
            return VerificationResult(
                provider="nsc",
                status=VerificationStatus.NOT_FOUND,
                verified_name=f"{first_name} {last_name}",
                raw=payload,
            )
        best = _best_match(verifications, expected_degree)
        return VerificationResult(
            provider="nsc",
            status=VerificationStatus.VERIFIED,
            external_ref=best.get("verification_id"),
            verified_name=f"{first_name} {last_name}",
            credential=best.get("degree"),
            issue_date=best.get("conferred_date"),
            raw=payload,
        )
    except Exception as e:
        logger.warning(f"NSC verify failed: {e}")
        return VerificationResult(
            provider="nsc",
            status=VerificationStatus.ERROR,
            raw={"exception": str(e)},
        )


# ---------------------------------------------------------------------------
def _best_match(verifications: list[dict], expected: str) -> dict:
    if not expected:
        return verifications[0]
    target = expected.lower()
    for v in verifications:
        if target in (v.get("degree") or "").lower():
            return v
    return verifications[0]


def _stub(first_name: str, last_name: str, expected_degree: str) -> VerificationResult:
    """Deterministic stub: verified for names starting A-U, not_found for V-Z."""
    if not last_name or last_name[0].upper() >= "V":
        return VerificationResult(
            provider="nsc",
            status=VerificationStatus.NOT_FOUND,
            verified_name=f"{first_name} {last_name}",
            stubbed=True,
            raw={"note": "NSC service key not configured — this is a stubbed result."},
        )
    return VerificationResult(
        provider="nsc",
        status=VerificationStatus.VERIFIED,
        external_ref=f"stub-{last_name.upper()}-{first_name[:1].upper()}",
        verified_name=f"{first_name} {last_name}",
        credential=expected_degree or "Associate of Applied Science",
        issue_date="2024-05-15",
        stubbed=True,
        raw={
            "note": "NSC service key not configured — this is a stubbed result.",
            "would_call": f"{_BASE}/degreeverify/v1/verify",
        },
    )
