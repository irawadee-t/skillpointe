"""
test_admin_search.py — GET /admin/search (combined typeahead for the admin top bar).

Covers:
  1. Admin gets grouped results (applicants / employers / credentials).
  2. Partial, case-insensitive matching is delegated to ILIKE %q% params.
  3. Non-admin roles are rejected.
  4. Empty q is rejected (min_length=1) — searching starts at the first character.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_admin
from app.auth.schemas import CurrentUser
from app.main import app


def _admin_user() -> CurrentUser:
    return CurrentUser(
        user_id="admin-user-id",
        email="admin@test.com",
        role="admin",
        onboarding_complete=True,
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _mock_db_context(fetch_side_effect):
    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=fetch_side_effect)

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.admin.get_db", return_value=mock_ctx), conn


APPLICANT_ROWS = [
    {
        "id": "a1", "first_name": "Jane", "last_name": "Doe",
        "email": "jane@test.local", "city": "Austin", "state": "TX",
    },
]
EMPLOYER_ROWS = [
    {"id": "e1", "name": "Southwire", "industry": "Manufacturing", "city": "Carrollton", "state": "GA"},
]
CREDENTIAL_ROWS = [
    {
        "id": "c1", "name": "EPA 608", "issuer": "EPA",
        "first_name": "Jane", "last_name": "Doe", "email": "jane@test.local",
    },
]


class TestAdminSearch:
    def test_grouped_results(self, client: TestClient) -> None:
        app.dependency_overrides[require_admin] = _admin_user
        ctx_patch, conn = _mock_db_context([APPLICANT_ROWS, EMPLOYER_ROWS, CREDENTIAL_ROWS])
        with ctx_patch:
            res = client.get("/admin/search", params={"q": "ja"})
        assert res.status_code == 200
        body = res.json()

        assert [r["label"] for r in body["applicants"]] == ["Jane Doe"]
        assert body["applicants"][0]["href"] == "/admin/applicants?q=jane%40test.local"
        assert body["applicants"][0]["subtitle"] == "jane@test.local, Austin, TX"

        assert [r["label"] for r in body["employers"]] == ["Southwire"]
        assert body["employers"][0]["href"] == "/admin/employers/e1"

        assert [r["label"] for r in body["credentials"]] == ["EPA 608"]
        assert body["credentials"][0]["subtitle"] == "EPA, Jane Doe"

        # All three queries received the ILIKE pattern for partial matching.
        for call in conn.fetch.await_args_list:
            assert "%ja%" in call.args

    def test_empty_groups_are_lists(self, client: TestClient) -> None:
        app.dependency_overrides[require_admin] = _admin_user
        ctx_patch, _ = _mock_db_context([[], [], []])
        with ctx_patch:
            res = client.get("/admin/search", params={"q": "zzz"})
        assert res.status_code == 200
        assert res.json() == {"applicants": [], "employers": [], "credentials": []}

    def test_single_character_query_allowed(self, client: TestClient) -> None:
        """Type-ahead starts from the FIRST character."""
        app.dependency_overrides[require_admin] = _admin_user
        ctx_patch, conn = _mock_db_context([[], [], []])
        with ctx_patch:
            res = client.get("/admin/search", params={"q": "j"})
        assert res.status_code == 200
        for call in conn.fetch.await_args_list:
            assert "%j%" in call.args

    def test_missing_query_rejected(self, client: TestClient) -> None:
        app.dependency_overrides[require_admin] = _admin_user
        res = client.get("/admin/search")
        assert res.status_code == 422

    def test_requires_admin(self, client: TestClient) -> None:
        # No override — the real dependency rejects an unauthenticated request.
        res = client.get("/admin/search", params={"q": "ja"})
        assert res.status_code in (401, 403)
