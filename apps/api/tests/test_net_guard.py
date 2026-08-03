"""SSRF egress-guard tests — the guard that stops user-supplied URLs (job-import
careers pages, badge links) from reaching internal/metadata endpoints."""
import ipaddress
from unittest.mock import patch

import pytest

from app.util.net_guard import BlockedURLError, validate_public_url


def _resolves_to(ip: str):
    """Patch DNS so a hostname resolves to a chosen IP for the test."""
    return patch(
        "app.util.net_guard.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", (ip, 443))],
    )


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",   # cloud metadata (IAM creds)
    "http://localhost:8000/admin",                 # loopback by name
    "http://127.0.0.1/",                           # loopback literal
    "http://10.0.0.5/internal",                    # RFC-1918 literal
    "http://192.168.1.1/",                         # RFC-1918 literal
    "http://[::1]/",                               # IPv6 loopback
])
def test_blocks_private_and_metadata_targets(url):
    with pytest.raises(BlockedURLError):
        validate_public_url(url)


@pytest.mark.parametrize("url", [
    "ftp://example.com/x",       # non-http scheme
    "file:///etc/passwd",        # file scheme
    "gopher://127.0.0.1:70/",    # gopher scheme
    "not-a-url",                 # no scheme/host
])
def test_blocks_bad_schemes(url):
    with pytest.raises(BlockedURLError):
        validate_public_url(url)


def test_blocks_hostname_resolving_to_private_ip():
    # A public-looking hostname that (via DNS) points at an internal address.
    with _resolves_to("10.1.2.3"):
        with pytest.raises(BlockedURLError):
            validate_public_url("https://sneaky.example.com/")


def test_allows_public_hostname():
    with _resolves_to("93.184.216.34"):  # a public address
        assert validate_public_url("https://example.com/careers") == "https://example.com/careers"


def test_public_ip_literal_passes():
    assert ipaddress.ip_address("93.184.216.34").is_global
    assert validate_public_url("https://93.184.216.34/") == "https://93.184.216.34/"
