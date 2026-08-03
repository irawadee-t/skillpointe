"""
Input-validation edge cases — the rules a user should never be able to break.

These tests exercise Pydantic request-model validation, which runs BEFORE the
route handler body, so no database is needed: the mocked Supabase client only
satisfies the auth dependency's role lookup.

Covered rules:
  1.  Credential expires_date < issued_date            → 422
  2.  Credential blank raw_name                        → 422
  3.  Job pay_min > pay_max                            → 422
  4.  Job negative pay                                 → 422
  5.  Job oversize title (>200 chars)                  → 422
  6.  Job invalid work_setting enum                    → 422
  7.  Interview slot end_at <= start_at                → 422
  8.  Interview slot start_at in the past              → 422
  9.  Oversize chat message (>5000 chars)              → 422
  10. Blank / oversize DM content                      → 422
  11. Outreach blank subject                           → 422
  12. Profile gpa out of range + malformed date        → 422
Plus happy-path model checks so valid payloads still parse.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


def _grant_role(mock_supabase_client: MagicMock, role: str) -> None:
    """Make the auth dependency's user_profiles lookup return the given role."""
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"role": role, "onboarding_complete": True}
    ]


@pytest.fixture
def applicant_client(client: TestClient, mock_supabase_client: MagicMock):
    _grant_role(mock_supabase_client, "applicant")
    return client


@pytest.fixture
def employer_client(client: TestClient, mock_supabase_client: MagicMock):
    _grant_role(mock_supabase_client, "employer")
    return client


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1–2. Credentials
# ---------------------------------------------------------------------------

def test_credential_expires_before_issued_rejected(applicant_client, applicant_token):
    resp = applicant_client.post(
        "/applicant/me/credentials",
        headers=_auth(applicant_token),
        json={"raw_name": "EPA 608", "issued_date": "2026-07-14", "expires_date": "2026-07-08"},
    )
    assert resp.status_code == 422
    assert "expires_date" in resp.text


def test_credential_blank_name_rejected(applicant_client, applicant_token):
    resp = applicant_client.post(
        "/applicant/me/credentials",
        headers=_auth(applicant_token),
        json={"raw_name": "   ", "issued_date": "2026-01-01"},
    )
    assert resp.status_code == 422


def test_credential_valid_dates_parse():
    from app.routers.credentials import CredentialIn

    model = CredentialIn(raw_name="OSHA 30", issued_date="2025-01-01", expires_date="2027-01-01")
    assert model.raw_name == "OSHA 30"


# ---------------------------------------------------------------------------
# 3–6. Jobs create / update
# ---------------------------------------------------------------------------

def test_job_pay_min_greater_than_pay_max_rejected(employer_client, employer_token):
    resp = employer_client.post(
        "/employer/me/jobs",
        headers=_auth(employer_token),
        json={"title_raw": "Electrician", "pay_min": 40, "pay_max": 20},
    )
    assert resp.status_code == 422
    assert "pay_min" in resp.text


def test_job_negative_pay_rejected(employer_client, employer_token):
    resp = employer_client.post(
        "/employer/me/jobs",
        headers=_auth(employer_token),
        json={"title_raw": "Electrician", "pay_min": -5},
    )
    assert resp.status_code == 422


def test_job_oversize_title_rejected(employer_client, employer_token):
    resp = employer_client.post(
        "/employer/me/jobs",
        headers=_auth(employer_token),
        json={"title_raw": "X" * 201},
    )
    assert resp.status_code == 422


def test_job_invalid_work_setting_rejected(employer_client, employer_token):
    resp = employer_client.post(
        "/employer/me/jobs",
        headers=_auth(employer_token),
        json={"title_raw": "Electrician", "work_setting": "underwater"},
    )
    assert resp.status_code == 422


def test_job_update_pay_inversion_rejected(employer_client, employer_token):
    resp = employer_client.patch(
        "/employer/me/jobs/00000000-0000-0000-0000-000000000001",
        headers=_auth(employer_token),
        json={"pay_min": 90, "pay_max": 10},
    )
    assert resp.status_code == 422


def test_job_equal_pay_bounds_parse():
    from app.schemas.employer import JobCreateRequest

    model = JobCreateRequest(title_raw="Welder", pay_min=25, pay_max=25, work_setting="on_site")
    assert model.pay_min == model.pay_max == 25


# ---------------------------------------------------------------------------
# 7–8. Interview slots
# ---------------------------------------------------------------------------

def test_interview_slot_end_before_start_rejected(employer_client, employer_token):
    start = datetime.now() + timedelta(days=2)
    end = start - timedelta(hours=1)
    resp = employer_client.post(
        "/employer/me/applications/00000000-0000-0000-0000-000000000001/propose",
        headers=_auth(employer_token),
        json={"slots": [{"start_at": start.isoformat(), "end_at": end.isoformat()}]},
    )
    assert resp.status_code == 422
    assert "end_at" in resp.text


def test_interview_slot_in_the_past_rejected(employer_client, employer_token):
    start = datetime.now() - timedelta(days=2)
    end = start + timedelta(hours=1)
    resp = employer_client.post(
        "/employer/me/applications/00000000-0000-0000-0000-000000000001/propose",
        headers=_auth(employer_token),
        json={"slots": [{"start_at": start.isoformat(), "end_at": end.isoformat()}]},
    )
    assert resp.status_code == 422
    assert "past" in resp.text


def test_interview_slot_valid_window_parses():
    from app.routers.interviews import SlotProposal

    start = datetime.now() + timedelta(days=1)
    model = SlotProposal(start_at=start, end_at=start + timedelta(hours=1))
    assert model.end_at > model.start_at


# ---------------------------------------------------------------------------
# 9. Chat message size
# ---------------------------------------------------------------------------

def test_chat_message_oversize_rejected(applicant_client, applicant_token):
    resp = applicant_client.post(
        "/applicant/me/chat/sessions/00000000-0000-0000-0000-000000000001/messages",
        headers=_auth(applicant_token),
        json={"content": "y" * 5001},
    )
    assert resp.status_code == 422


def test_chat_message_blank_rejected(applicant_client, applicant_token):
    resp = applicant_client.post(
        "/applicant/me/chat/sessions/00000000-0000-0000-0000-000000000001/messages",
        headers=_auth(applicant_token),
        json={"content": "   "},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 10. Direct messages
# ---------------------------------------------------------------------------

def test_dm_oversize_rejected(applicant_client, applicant_token):
    resp = applicant_client.post(
        "/conversations/00000000-0000-0000-0000-000000000001/messages",
        headers=_auth(applicant_token),
        json={"content": "z" * 5001},
    )
    assert resp.status_code == 422


def test_dm_blank_rejected(applicant_client, applicant_token):
    resp = applicant_client.post(
        "/conversations/00000000-0000-0000-0000-000000000001/messages",
        headers=_auth(applicant_token),
        json={"content": ""},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 11. Outreach
# ---------------------------------------------------------------------------

def test_outreach_blank_subject_rejected(employer_client, employer_token):
    resp = employer_client.post(
        "/employer/me/outreach/send",
        headers=_auth(employer_token),
        json={
            "match_id": "m1", "applicant_id": "a1", "job_id": "j1",
            "subject": "   ", "body": "Hello there",
        },
    )
    assert resp.status_code == 422


def test_outreach_oversize_body_rejected(employer_client, employer_token):
    resp = employer_client.post(
        "/employer/me/outreach/send",
        headers=_auth(employer_token),
        json={
            "match_id": "m1", "applicant_id": "a1", "job_id": "j1",
            "subject": "Opportunity", "body": "b" * 5001,
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 12. Applicant profile
# ---------------------------------------------------------------------------

def test_profile_gpa_out_of_range_rejected(applicant_client, applicant_token):
    resp = applicant_client.patch(
        "/applicant/me/profile",
        headers=_auth(applicant_token),
        json={"gpa": 9.2},
    )
    assert resp.status_code == 422


def test_profile_malformed_date_rejected(applicant_client, applicant_token):
    resp = applicant_client.patch(
        "/applicant/me/profile",
        headers=_auth(applicant_token),
        json={"available_from_date": "not-a-date"},
    )
    assert resp.status_code == 422


def test_profile_oversize_name_rejected(applicant_client, applicant_token):
    resp = applicant_client.patch(
        "/applicant/me/profile",
        headers=_auth(applicant_token),
        json={"first_name": "A" * 121},
    )
    assert resp.status_code == 422
