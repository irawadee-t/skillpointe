"""Unit tests for the SFTP/file-drop CSV parser and the SIS mock provider."""
from datetime import date

from app.skilled_pro import file_lane
from app.integrations.sis import get_sis_provider, MockSISProvider, SISRecord


def test_parse_csv_happy_path_with_aliases():
    csv = "Email,Credential,Issuer,Issued\n a@b.com , Welding Cert , Acme , 2025-01-01 \n"
    parsed = file_lane.parse_csv(csv)
    assert parsed.skipped == 0
    assert parsed.rows[0]["email"] == "a@b.com"
    assert parsed.rows[0]["credential_name"] == "Welding Cert"
    assert parsed.rows[0]["issuer"] == "Acme"
    assert parsed.rows[0]["issued_date"] == "2025-01-01"


def test_parse_csv_skips_rows_missing_required():
    csv = "email,credential_name\nonly@email.com,\n,Some Cert\ngood@x.com,Real Cert\n"
    parsed = file_lane.parse_csv(csv)
    assert parsed.skipped == 2
    assert len(parsed.rows) == 1
    assert parsed.rows[0]["email"] == "good@x.com"


def test_parse_csv_empty_optional_fields_become_none():
    parsed = file_lane.parse_csv("email,credential_name\nx@y.com,Cert\n")
    assert parsed.rows[0]["issuer"] is None
    assert parsed.rows[0]["issued_date"] is None


def test_sis_default_is_mock():
    assert isinstance(get_sis_provider(), MockSISProvider)


def test_sis_mock_feed_is_deterministic_and_targets_seeded_user():
    recs = MockSISProvider().fetch_records()
    assert all(isinstance(r, SISRecord) for r in recs)
    emails = [r.email for r in recs]
    assert "applicant@test.local" in emails        # seeded -> will match
    assert any("@example" in e for e in emails)     # an unmatched row is included
    assert recs[0].issued_date == date(2025, 5, 15)
