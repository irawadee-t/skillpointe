"""
Outbound-request (SSRF) egress guard.

Any time the server fetches a URL that a *user* supplied — a careers-page URL to
scrape, a badge-assertion link to verify — an attacker can point it at internal
infrastructure: the cloud metadata endpoint (169.254.169.254 → IAM credentials),
loopback admin ports, or RFC-1918 hosts behind the app. This module blocks that.

Two layers, use both where you can:
  1. ``validate_public_url`` — parse, restrict the scheme, DNS-resolve the host,
     and reject the request if ANY resolved address is private/loopback/link-
     local/reserved. (Resolving *all* records defeats a DNS answer that mixes a
     public and an internal address.)
  2. ``safe_get`` / ``safe_get_sync`` — fetch with redirects DISABLED and
     re-validate every hop's ``Location`` before following it, so an allowlisted
     or public host cannot 302 the request onto an internal target.

Residual risk: DNS rebinding between validate and connect (TOCTOU). Pinning the
resolved IP into the socket would close it fully; validating resolved addresses
is the standard, high-bar mitigation and is what we do here.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

_ALLOWED_SCHEMES = ("http", "https")
_MAX_REDIRECTS = 4


class BlockedURLError(ValueError):
    """Raised when a URL is not allowed to be fetched (bad scheme or private target)."""


def _address_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def validate_public_url(url: str, *, allowed_schemes: tuple[str, ...] = _ALLOWED_SCHEMES) -> str:
    """Return the URL if it is safe to fetch, else raise BlockedURLError.

    Enforces the scheme allowlist and that the host resolves ONLY to public IPs.
    """
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in allowed_schemes:
        raise BlockedURLError(f"scheme {parsed.scheme!r} not allowed")
    host = parsed.hostname
    if not host:
        raise BlockedURLError("URL has no host")

    # An IP literal: check it directly (no DNS).
    try:
        if not _address_is_public(str(ipaddress.ip_address(host))):
            raise BlockedURLError(f"host {host} is a non-public address")
        return url
    except ValueError:
        pass  # not a literal IP — resolve it below

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedURLError(f"could not resolve host {host}: {exc}") from exc
    resolved = {info[4][0] for info in infos}
    if not resolved:
        raise BlockedURLError(f"host {host} did not resolve")
    for ip in resolved:
        if not _address_is_public(ip):
            raise BlockedURLError(f"host {host} resolves to non-public address {ip}")
    return url


def _check_hop(url: str, host_check) -> None:
    validate_public_url(url)
    if host_check is not None and not host_check(url):
        raise BlockedURLError(f"host not allowed: {url}")


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    host_check=None,
    max_redirects: int = _MAX_REDIRECTS,
    **kwargs,
) -> httpx.Response:
    """GET with SSRF-safe manual redirect handling (async).

    Each URL — the initial one and every redirect target — is validated as a
    public address (and against ``host_check`` if given) BEFORE it is fetched.
    Pass an ``httpx.AsyncClient`` created WITHOUT ``follow_redirects=True``.
    """
    current = url
    for _ in range(max_redirects + 1):
        _check_hop(current, host_check)
        resp = await client.get(current, follow_redirects=False, **kwargs)
        if resp.is_redirect and resp.headers.get("location"):
            current = str(resp.next_request.url) if resp.next_request else resp.headers["location"]
            continue
        return resp
    raise BlockedURLError("too many redirects")


def safe_get_sync(url: str, *, host_check=None, max_redirects: int = _MAX_REDIRECTS, **kwargs) -> httpx.Response:
    """GET with SSRF-safe manual redirect handling (sync). See ``safe_get``."""
    current = url
    with httpx.Client(follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            _check_hop(current, host_check)
            resp = client.get(current, **kwargs)
            if resp.is_redirect and resp.headers.get("location"):
                current = str(resp.next_request.url) if resp.next_request else resp.headers["location"]
                continue
            return resp
    raise BlockedURLError("too many redirects")
