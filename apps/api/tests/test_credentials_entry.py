"""
Structured credential entry — category taxonomy validation — and the
simulated-Checkr response contract (no fabricated external URL).
"""
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.integrations import checkr
from app.routers.credentials import CredentialIn
from app.skilled_pro.taxonomy import CredentialType

# ---------------------------------------------------------------------------
# Category taxonomy (CTDL-grounded: certification / license / degree /
# apprenticeship / safety / union / other)
# ---------------------------------------------------------------------------

VALID_CATEGORIES = [
    "certification", "license", "degree", "apprenticeship", "safety", "union", "other",
]


def test_category_accepts_full_taxonomy():
    for cat in VALID_CATEGORIES:
        cred = CredentialIn(raw_name="OSHA 30", category=cat)
        assert cred.category == CredentialType(cat)


def test_category_rejects_unknown_values():
    with pytest.raises(ValidationError):
        CredentialIn(raw_name="OSHA 30", category="masterclass")


def test_category_optional_for_legacy_clients():
    assert CredentialIn(raw_name="OSHA 30").category is None


def test_taxonomy_enum_matches_documented_set():
    assert sorted(t.value for t in CredentialType) == sorted(VALID_CATEGORIES)


def test_credential_url_must_be_http():
    with pytest.raises(ValidationError):
        CredentialIn(raw_name="OSHA 30", credential_url="javascript:alert(1)")
    ok = CredentialIn(raw_name="OSHA 30", credential_url="https://example.com/verify/123")
    assert ok.credential_url == "https://example.com/verify/123"


def test_blank_credential_url_normalizes_to_none():
    assert CredentialIn(raw_name="OSHA 30", credential_url="  ").credential_url is None


# ---------------------------------------------------------------------------
# Simulated Checkr — local dev without an API key must NOT fabricate a hosted
# invitation URL (a fake apply.checkr.com link 404s with "Account not found").
# ---------------------------------------------------------------------------

class _LocalSettings:
    checkr_api_key = ""
    checkr_webhook_secret = ""
    checkr_default_package = "driver_pro"
    is_local = True


async def test_simulated_checkr_invitation_has_no_external_url():
    with patch("app.integrations.checkr.get_settings", return_value=_LocalSettings()):
        inv = await checkr.create_invitation(
            email="worker@example.com", first_name="Val", last_name="Worker",
        )
    assert inv.simulated is True
    assert inv.invitation_url == ""
    assert inv.candidate_id.startswith("sim_cand_")
    assert inv.package == "driver_pro"


# ---------------------------------------------------------------------------
# checkr.is_configured() — the single source of truth behind the UI's
# `checkr_enabled` flag (GET /applicant/me/credentials/verify-config).
# Unset or .env.example placeholder keys must read as "not configured" so the
# verify panel never offers a background check that dead-ends.
# ---------------------------------------------------------------------------

class _KeySettings:
    def __init__(self, key: str):
        self.checkr_api_key = key


@pytest.mark.parametrize("key", [
    "",                       # unset
    "   ",                    # whitespace only
    "your-checkr-api-key",    # .env.example placeholder
    "YOUR_CHECKR_KEY",        # placeholder, different casing/separator
    "changeme",
    "placeholder",
    "xxx",
])
def test_checkr_not_configured_for_unset_or_placeholder_keys(key: str):
    with patch("app.integrations.checkr.get_settings", return_value=_KeySettings(key)):
        assert checkr.is_configured() is False


def test_checkr_configured_with_real_looking_key():
    with patch(
        "app.integrations.checkr.get_settings",
        return_value=_KeySettings("sk_test_a1b2c3d4e5f6a7b8c9d0"),
    ):
        assert checkr.is_configured() is True
