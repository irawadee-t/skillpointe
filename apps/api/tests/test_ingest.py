"""
Unit tests for the bulk credential ingestion planner (pure logic — no DB).
"""
from app.skilled_pro.ingest import IngestRowInput, plan_row
from app.skilled_pro.verification import (
    CredentialSource,
    VerificationEvidence,
    VerificationLevel,
    derive_level,
)


def test_valid_row_normalizes():
    p = plan_row(IngestRowInput(email="Jane@Example.com", credential_name="EPA 608"))
    assert p.ok
    assert p.email == "jane@example.com"          # normalized
    assert p.canonical_code == "EPA_608"
    assert not p.needs_review


def test_unknown_credential_flagged_for_review():
    p = plan_row(IngestRowInput(email="a@b.com", credential_name="basket weaving lvl 7"))
    assert p.ok
    assert p.canonical_code is None
    assert p.needs_review                          # trusted source, but no taxonomy match


def test_missing_email():
    p = plan_row(IngestRowInput(email="", credential_name="EPA 608"))
    assert not p.ok and p.error == "Missing email"


def test_invalid_email():
    p = plan_row(IngestRowInput(email="not-an-email", credential_name="EPA 608"))
    assert not p.ok and p.error == "Invalid email"


def test_missing_credential_name():
    p = plan_row(IngestRowInput(email="a@b.com", credential_name="  "))
    assert not p.ok and p.error == "Missing credential name"


def test_ingest_level_is_institution_verified():
    # The ingestion lane must produce Institution-Verified, not Self-Reported.
    lvl = derive_level(VerificationEvidence(source=CredentialSource.PARTNER_PORTAL))
    assert lvl == VerificationLevel.INSTITUTION_VERIFIED
    assert lvl.value == 1
