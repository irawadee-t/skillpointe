"""
Digital-badge verification — Credly and Open Badges (2.0/3.0).

A worker pastes the public URL of a badge they earned (Credly, NCCER's Credly
issuer, Badgr/Canvas, or a hosted Open Badge assertion). We fetch it, confirm it
is a real, currently-valid assertion, and extract the issuer, badge name, earner
name, and issue date. Because the issuer cryptographically/authoritatively hosts
the assertion, a confirmed badge is *registry-grade* trust — the highest-value,
lowest-cost verification tier for trades (NCCER already issues through Credly).

SSRF safety: only a fixed allowlist of badge-provider hosts is ever fetched, so a
pasted URL can't be used to probe internal services. Network failures degrade to
``ok=False`` rather than raising.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

import httpx

from app.util.net_guard import safe_get

# Only these hosts (and subdomains) are ever fetched — the SSRF guard.
_ALLOWED_HOSTS: tuple[str, ...] = (
    "credly.com",
    "youracclaim.com",   # legacy Credly domain
    "badgr.com",
    "badgr.io",
    "canvas.instructure.com",
    "openbadgefactory.com",
    "openbadges.org",
    "nccer.org",
)

_TIMEOUT = httpx.Timeout(8.0)


@dataclass(frozen=True)
class BadgeVerification:
    ok: bool
    provider: str = "badge"
    issuer: str | None = None
    badge_name: str | None = None
    earner_name: str | None = None
    issued_on: date | None = None
    accepted: bool = False
    detail: str = ""
    url: str = ""


def _host_allowed(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS)


def _parse_iso_date(val: str | None) -> date | None:
    if not val:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(val))
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _extract_ldjson(html: str) -> dict | None:
    """Pull the first application/ld+json / embedded badge JSON out of an HTML page."""
    for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1).strip())
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return None


def _from_credly_payload(data: dict, url: str) -> BadgeVerification:
    """Normalize a Credly badge-assertion JSON payload."""
    d = data.get("data", data)  # Credly wraps in {"data": {...}}
    badge_tmpl = d.get("badge_template") or d.get("badge") or {}
    issuer = (
        (badge_tmpl.get("issuer") or {}).get("name")
        or (d.get("issuer") or {}).get("name")
        or (d.get("issuer_organization") or {}).get("name")
    )
    name = badge_tmpl.get("name") or d.get("name")
    earner = d.get("issued_to") or d.get("recipient_name") or (d.get("user") or {}).get("full_name")
    issued = _parse_iso_date(d.get("issued_at") or d.get("issued_on") or d.get("issuedOn"))
    state = (d.get("state") or "").lower()
    accepted = state in ("accepted", "issued", "") and not d.get("revoked", False)
    ok = bool(name and issuer)
    return BadgeVerification(
        ok=ok, provider="credly", issuer=issuer, badge_name=name, earner_name=earner,
        issued_on=issued, accepted=accepted, url=url,
        detail="" if ok else "could not read badge name/issuer",
    )


def _from_openbadge_payload(data: dict, url: str) -> BadgeVerification:
    """Normalize an Open Badges 2.0/3.0 assertion (JSON-LD)."""
    # OB 3.0 credentialSubject / achievement, or OB 2.0 badge + recipient.
    cred = data.get("credentialSubject") or {}
    achievement = cred.get("achievement") or data.get("badge") or {}
    if isinstance(achievement, str):
        achievement = {}
    issuer_obj = data.get("issuer") or achievement.get("issuer") or {}
    issuer = issuer_obj.get("name") if isinstance(issuer_obj, dict) else None
    name = achievement.get("name") if isinstance(achievement, dict) else None
    earner = cred.get("name") or (data.get("recipient") or {}).get("name")
    issued = _parse_iso_date(data.get("issuedOn") or data.get("validFrom") or data.get("issuanceDate"))
    revoked = bool(data.get("revoked", False))
    ok = bool(name and issuer)
    return BadgeVerification(
        ok=ok, provider="openbadge", issuer=issuer, badge_name=name, earner_name=earner,
        issued_on=issued, accepted=not revoked, url=url,
        detail="" if ok else "could not read achievement/issuer",
    )


async def verify_badge_url(url: str) -> BadgeVerification:
    """Fetch and validate a badge URL. Never raises — returns ok=False on failure."""
    url = (url or "").strip()
    if not url:
        return BadgeVerification(ok=False, detail="No badge URL provided", url=url)
    if not _host_allowed(url):
        return BadgeVerification(
            ok=False, url=url,
            detail="Unsupported badge host. Paste a Credly, Badgr, Canvas, or Open Badges link.",
        )

    try:
        # follow_redirects stays OFF here — safe_get re-checks every redirect hop
        # against BOTH the public-IP guard and the badge-host allowlist, so an
        # allowlisted host can't 302 us onto an internal address.
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # Ask for JSON first; fall back to the HTML page's embedded JSON-LD.
            resp = await safe_get(
                client, url, host_check=_host_allowed,
                headers={"Accept": "application/json, text/html"},
            )
    except Exception as exc:
        return BadgeVerification(ok=False, url=url, detail=f"Could not reach badge provider: {exc}")

    if resp.status_code == 404:
        return BadgeVerification(ok=False, url=url, detail="Badge not found. Check the link.")
    if resp.status_code >= 400:
        return BadgeVerification(ok=False, url=url, detail=f"Badge provider returned {resp.status_code}.")

    ctype = resp.headers.get("content-type", "")
    data: dict | None = None
    if "json" in ctype:
        try:
            data = resp.json()
        except Exception:
            data = None
    if data is None:
        data = _extract_ldjson(resp.text)
    if data is None:
        return BadgeVerification(ok=False, url=url, detail="Could not read badge data from that link.")

    host = (urlparse(url).hostname or "").lower()
    if "credly" in host or "acclaim" in host:
        result = _from_credly_payload(data, url)
    else:
        result = _from_openbadge_payload(data, url)

    if result.ok and not result.accepted:
        return BadgeVerification(ok=False, provider=result.provider, url=url,
                                 detail="This badge has been revoked or isn't accepted.")
    return result
