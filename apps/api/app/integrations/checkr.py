"""
Checkr integration — background checks, MVR/CDLIS, and professional-license
verification for skilled-trades hiring.

Checkr is the industry standard for hiring/gig platforms and, critically, acts as
the Consumer Reporting Agency: it owns the FCRA disclosure / authorization /
adverse-action flow. Our platform only kicks off a *hosted invitation* — the
worker completes ID + consent on Checkr's own screens — and later receives the
report result via webhook. That keeps SkillPointe out of CRA territory.

Flow:
  1. create_candidate(email, names)        -> candidate_id
  2. create_invitation(candidate_id, pkg)  -> {invitation_id, invitation_url}
     (the worker opens invitation_url and completes the check)
  3. Checkr POSTs webhooks (report.completed, ...) -> map to clear/consider

When CHECKR_API_KEY is unset the client returns a *simulated* invitation in local
dev (so the flow is demoable) and raises IntegrationNotConfigured in deployed
environments — never a silent fake.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.integrations import IntegrationNotConfigured

_BASE = "https://api.checkr.com/v1"
_TIMEOUT = httpx.Timeout(12.0)


@dataclass(frozen=True)
class CheckrInvitation:
    candidate_id: str
    invitation_id: str
    invitation_url: str
    package: str
    simulated: bool = False


def _auth() -> tuple[str, str]:
    # Checkr uses HTTP Basic with the secret key as the username, blank password.
    return (get_settings().checkr_api_key, "")


def is_configured() -> bool:
    """True only when a REAL Checkr API key is set.

    Single source of truth for "is Checkr actually usable": `create_invitation`
    simulates/refuses on it, and the UI hides the background-check method when
    it is False. Mirrors app.util.openai_client — .env.example placeholder
    values ("your-...", "changeme", ...) count as not configured, so a copied
    template never sends workers into a dead-end Checkr flow.
    """
    key = (get_settings().checkr_api_key or "").strip()
    if not key:
        return False
    return not key.lower().startswith(("your-", "your_", "changeme", "placeholder", "xxx"))


async def create_invitation(
    *, email: str, first_name: str, last_name: str, package: str | None = None
) -> CheckrInvitation:
    """Create a Checkr candidate + hosted invitation. Returns the URL the worker
    completes. Simulated in local dev when no key is set; refuses in prod."""
    settings = get_settings()
    pkg = package or settings.checkr_default_package

    if not is_configured():
        if settings.is_local:
            # Simulated invitation so the UI flow is demoable. Deliberately NO
            # invitation_url: a fabricated apply.checkr.com link 404s on Checkr's
            # side ("Account not found"), so the caller must render an inline
            # not-enabled state instead of sending the worker off-site.
            fake = hashlib.sha256(email.encode()).hexdigest()[:12]
            return CheckrInvitation(
                candidate_id=f"sim_cand_{fake}",
                invitation_id=f"sim_inv_{fake}",
                invitation_url="",
                package=pkg, simulated=True,
            )
        raise IntegrationNotConfigured(
            "Checkr is not configured. Set CHECKR_API_KEY to enable background checks."
        )

    async with httpx.AsyncClient(timeout=_TIMEOUT, auth=_auth()) as client:
        cand = await client.post(
            f"{_BASE}/candidates",
            data={"email": email, "first_name": first_name, "last_name": last_name},
        )
        cand.raise_for_status()
        candidate_id = cand.json()["id"]

        inv = await client.post(
            f"{_BASE}/invitations",
            data={"candidate_id": candidate_id, "package": pkg},
        )
        inv.raise_for_status()
        ij = inv.json()

    return CheckrInvitation(
        candidate_id=candidate_id,
        invitation_id=ij.get("id", ""),
        invitation_url=ij.get("invitation_url", ""),
        package=pkg,
    )


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    """Validate the X-Checkr-Signature HMAC-SHA256 over the raw request body.
    Returns True when no secret is configured in local dev (so webhooks can be
    exercised), False on mismatch elsewhere."""
    secret = get_settings().checkr_webhook_secret
    if not secret:
        return get_settings().is_local
    if not signature:
        return False
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def status_from_report(result: str | None) -> str:
    """Map a Checkr report result to our credential status."""
    r = (result or "").lower()
    if r == "clear":
        return "clear"
    if r == "consider":
        return "consider"
    return "pending"
