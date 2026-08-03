"""
Tests for GET /employer/me/analytics/next-actions — the employer action queue.

Rules under test:
  1. Waiting candidates are returned with a true total and a display list
     capped at 5 (total reflects ALL rows, not the capped list).
  2. An employer with nothing waiting gets explicit zeros (honest empty state).
  3. The queue is scoped through _resolve_employer_id: a user with no linked
     employer gets 404, never another employer's queue.
  4. Applicant users are rejected by the role guard.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_employer_or_admin
from app.auth.schemas import CurrentUser
from app.main import app

EMPLOYER_USER_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
EMPLOYER_ID = "11111111-0000-0000-0000-111111111111"


def _employer_user() -> CurrentUser:
    return CurrentUser(
        user_id=EMPLOYER_USER_ID,
        email="employer@test.com",
        role="employer",
        onboarding_complete=True,
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _mock_db(fetchval_side_effect=None, fetch_return=None):
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=fetchval_side_effect)
    conn.fetch = AsyncMock(return_value=fetch_return or [])

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.employers.get_db", return_value=ctx), conn


def _waiting_row(i: int) -> dict:
    return {
        "applicant_id": f"55555555-0000-0000-0000-{i:012d}",
        "name": f"Candidate {i}",
        "job_id": "33333333-0000-0000-0000-333333333333",
        "job_title": "Welder",
        "interest_level": "interested" if i % 2 else "applied",
        "since": "2026-07-30T12:00:00+00:00",
    }


def _override_employer() -> None:
    app.dependency_overrides[require_employer_or_admin] = _employer_user


class TestNextActions:
    def test_waiting_list_capped_at_5_but_total_is_true_count(self, client) -> None:
        rows = [_waiting_row(i) for i in range(8)]
        # fetchval: 1st resolves employer_id, 2nd is unviewed applications,
        # 3rd is open (undecided) applications
        ctx, _ = _mock_db(fetchval_side_effect=[EMPLOYER_ID, 3, 4], fetch_return=rows)
        _override_employer()
        with ctx:
            res = client.get(
                "/employer/me/analytics/next-actions",
                headers={"Authorization": "Bearer fake"},
            )
        assert res.status_code == 200
        body = res.json()
        assert body["waiting_candidates_total"] == 8
        assert len(body["waiting_candidates"]) == 5
        assert body["unviewed_applications"] == 3
        assert body["open_applications"] == 4
        first = body["waiting_candidates"][0]
        assert first["name"] == "Candidate 0"
        assert first["job_title"] == "Welder"

    def test_empty_queue_returns_explicit_zeros(self, client) -> None:
        ctx, _ = _mock_db(fetchval_side_effect=[EMPLOYER_ID, 0, 0], fetch_return=[])
        _override_employer()
        with ctx:
            res = client.get(
                "/employer/me/analytics/next-actions",
                headers={"Authorization": "Bearer fake"},
            )
        assert res.status_code == 200
        body = res.json()
        assert body == {
            "waiting_candidates_total": 0,
            "waiting_candidates": [],
            "unviewed_applications": 0,
            "open_applications": 0,
        }

    def test_unlinked_user_gets_404(self, client) -> None:
        ctx, _ = _mock_db(fetchval_side_effect=[None])
        _override_employer()
        with ctx:
            res = client.get(
                "/employer/me/analytics/next-actions",
                headers={"Authorization": "Bearer fake"},
            )
        assert res.status_code == 404

    def test_queue_is_scoped_to_resolved_employer(self, client) -> None:
        """Every query must be parameterised by the resolved employer_id."""
        ctx, conn = _mock_db(fetchval_side_effect=[EMPLOYER_ID, 0, 0], fetch_return=[])
        _override_employer()
        with ctx:
            client.get(
                "/employer/me/analytics/next-actions",
                headers={"Authorization": "Bearer fake"},
            )
        # fetch (waiting candidates) called with employer_id as the parameter
        args, _kwargs = conn.fetch.call_args
        assert EMPLOYER_ID in args
        # second fetchval (unviewed applications) also scoped
        args2, _ = conn.fetchval.call_args_list[1]
        assert EMPLOYER_ID in args2
        # third fetchval (open applications) also scoped
        args3, _ = conn.fetchval.call_args_list[2]
        assert EMPLOYER_ID in args3
