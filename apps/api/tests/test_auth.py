"""
Tests for Phase 2 — Auth + RBAC.

Covers:
- JWT validation (valid, expired, bad audience, tampered)
- /auth/me returns correct user + role
- /auth/complete-signup creates profile (idempotent)
- Role enforcement: admin, applicant, employer
- 401 with no token, 403 with wrong role
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# JWT validation
# ---------------------------------------------------------------------------

def test_valid_jwt_accepted(client: TestClient, applicant_token: str, mock_supabase_client: MagicMock):
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "role": "applicant",
        "onboarding_complete": False,
    }
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {applicant_token}"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "applicant"


def test_expired_token_returns_401(client: TestClient, expired_token: str):
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_bad_audience_returns_401(client: TestClient, bad_audience_token: str):
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {bad_audience_token}"})
    assert resp.status_code == 401


def test_tampered_token_returns_401(client: TestClient):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer this.is.not.a.real.jwt"})
    assert resp.status_code == 401


def test_no_token_returns_403(client: TestClient):
    # HTTPBearer returns 403 when no Authorization header is present
    resp = client.get("/auth/me")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------

def test_me_returns_correct_role_admin(client: TestClient, admin_token: str, mock_supabase_client: MagicMock):
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "role": "admin",
        "onboarding_complete": True,
    }
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert body["email"] == "admin@example.com"
    assert body["onboarding_complete"] is True


def test_me_returns_correct_role_employer(client: TestClient, employer_token: str, mock_supabase_client: MagicMock):
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "role": "employer",
        "onboarding_complete": False,
    }
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {employer_token}"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "employer"


def test_me_returns_401_when_profile_not_found(client: TestClient, applicant_token: str, mock_supabase_client: MagicMock):
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {applicant_token}"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /auth/complete-signup
# ---------------------------------------------------------------------------

def test_complete_signup_creates_applicant_profile(client: TestClient, applicant_token: str, mock_supabase_client: MagicMock):
    # No existing profile
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None
    mock_supabase_client.table.return_value.insert.return_value.execute.return_value.data = [{"id": "new-id"}]
    mock_supabase_client.auth.admin.update_user_by_id.return_value = MagicMock()

    resp = client.post("/auth/complete-signup", headers={"Authorization": f"Bearer {applicant_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "applicant"
    assert body["already_existed"] is False


def test_complete_signup_is_idempotent(client: TestClient, applicant_token: str, mock_supabase_client: MagicMock):
    # Profile already exists
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "id": "existing-id",
        "role": "applicant",
    }
    resp = client.post("/auth/complete-signup", headers={"Authorization": f"Bearer {applicant_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "applicant"
    assert body["already_existed"] is True


def test_complete_signup_does_not_override_employer_role(client: TestClient, employer_token: str, mock_supabase_client: MagicMock):
    # Employer already has a profile with employer role
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "id": "existing-id",
        "role": "employer",
    }
    resp = client.post("/auth/complete-signup", headers={"Authorization": f"Bearer {employer_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "employer"   # role preserved, not overwritten to 'applicant'
    assert body["already_existed"] is True


# ---------------------------------------------------------------------------
# Role enforcement
# ---------------------------------------------------------------------------

def test_invite_employer_requires_admin_role(client: TestClient, applicant_token: str, mock_supabase_client: MagicMock):
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "role": "applicant",
        "onboarding_complete": False,
    }
    resp = client.post(
        "/auth/invite-employer",
        json={"email": "employer@example.com"},
        headers={"Authorization": f"Bearer {applicant_token}"},
    )
    assert resp.status_code == 403


def test_invite_employer_requires_admin_role_employer_blocked(client: TestClient, employer_token: str, mock_supabase_client: MagicMock):
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "role": "employer",
        "onboarding_complete": False,
    }
    resp = client.post(
        "/auth/invite-employer",
        json={"email": "another@example.com"},
        headers={"Authorization": f"Bearer {employer_token}"},
    )
    assert resp.status_code == 403
