"""
test_interest_signal.py — POST /applicant/me/matches/{id}/interest

Covers the set/update/clear semantics:
  - setting a level upserts saved_jobs and emits interest_set (+ apply_click for applied)
  - clicking the active pill sends interest_level=null → the saved_jobs row is
    DELETED and an interest_set event with interest_level null + previous_level
    is emitted — but only when something actually changed
  - invalid levels are rejected with 422

Mock-DB style (same approach as test_engagement_instrumentation.py): patch
get_db in the router module, override the auth dependency, then assert on the
SQL the endpoint executed.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_applicant
from app.auth.schemas import CurrentUser
from app.main import app

APPLICANT_USER_ID = "aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa"
APPLICANT_ID = "11111111-0000-0000-0000-111111111111"
JOB_ID = "33333333-0000-0000-0000-333333333333"
MATCH_ID = "77777777-0000-0000-0000-777777777777"


def _applicant_user() -> CurrentUser:
    return CurrentUser(
        user_id=APPLICANT_USER_ID,
        email="applicant@test.local",
        role="applicant",
        onboarding_complete=True,
    )


def _match_row() -> dict[str, Any]:
    return {"job_id": JOB_ID, "applicant_id": APPLICANT_ID}


def _mock_conn(
    fetchval_side: list[Any] | None = None,
    fetchrow_side: list[Any] | None = None,
):
    conn = AsyncMock()
    if fetchval_side is not None:
        conn.fetchval = AsyncMock(side_effect=fetchval_side)
    if fetchrow_side is not None:
        conn.fetchrow = AsyncMock(side_effect=fetchrow_side)
    conn.execute = AsyncMock(return_value="DELETE 1")
    # conn.transaction() is a sync call returning an async context manager.
    tx_ctx = MagicMock()
    tx_ctx.__aenter__ = AsyncMock(return_value=None)
    tx_ctx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_ctx)
    return conn


def _patch_db(conn: AsyncMock):
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=conn)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.applicants.get_db", return_value=mock_ctx)


def _executed_sql(conn: AsyncMock) -> str:
    return " ".join(str(c.args[0]) for c in conn.execute.call_args_list)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _auth():
    app.dependency_overrides[require_applicant] = _applicant_user
    yield
    app.dependency_overrides.clear()


def _post(client: TestClient, payload: dict[str, Any]):
    return client.post(
        f"/applicant/me/matches/{MATCH_ID}/interest",
        json=payload,
        headers={"Authorization": "Bearer fake"},
    )


class TestSetInterest:
    def test_set_level_upserts_and_emits_event(self, client: TestClient) -> None:
        conn = _mock_conn(
            fetchval_side=[None],  # no previous level
            fetchrow_side=[
                _match_row(),
                {"interest_level": "interested", "updated_at": "2026-07-21T00:00:00"},
            ],
        )
        with _patch_db(conn):
            res = _post(client, {"interest_level": "interested"})

        assert res.status_code == 200, res.text
        assert res.json()["interest_level"] == "interested"
        upsert_sql = str(conn.fetchrow.call_args_list[1].args[0])
        assert "INSERT INTO public.saved_jobs" in upsert_sql
        sql = _executed_sql(conn)
        assert "interest_set" in sql
        event_call = next(
            c for c in conn.execute.call_args_list if "interest_set" in str(c.args[0])
        )
        assert event_call.args[3]["interest_level"] == "interested"
        assert event_call.args[3]["previous_level"] is None

    def test_reclick_same_level_does_not_emit(self, client: TestClient) -> None:
        conn = _mock_conn(
            fetchval_side=["interested"],  # unchanged
            fetchrow_side=[
                _match_row(),
                {"interest_level": "interested", "updated_at": "2026-07-21T00:00:00"},
            ],
        )
        with _patch_db(conn):
            res = _post(client, {"interest_level": "interested"})

        assert res.status_code == 200, res.text
        assert "interest_set" not in _executed_sql(conn)

    def test_invalid_level_rejected(self, client: TestClient) -> None:
        conn = _mock_conn(fetchrow_side=[_match_row()])
        with _patch_db(conn):
            res = _post(client, {"interest_level": "maybe"})
        assert res.status_code == 422


class TestClearInterest:
    def test_null_deletes_row_and_emits_event_with_previous_level(
        self, client: TestClient
    ) -> None:
        conn = _mock_conn(
            fetchval_side=["interested"],  # previous level exists
            fetchrow_side=[_match_row()],
        )
        with _patch_db(conn):
            res = _post(client, {"interest_level": None})

        assert res.status_code == 200, res.text
        body = res.json()
        assert body["interest_level"] is None
        assert body["updated_at"] is None

        sql = _executed_sql(conn)
        assert "DELETE FROM public.saved_jobs" in sql
        assert "interest_set" in sql
        event_call = next(
            c for c in conn.execute.call_args_list if "interest_set" in str(c.args[0])
        )
        assert event_call.args[3]["interest_level"] is None
        assert event_call.args[3]["previous_level"] == "interested"
        # Clearing must never mint an apply_click.
        assert "apply_click" not in sql

    def test_null_with_no_existing_signal_is_noop_event_wise(
        self, client: TestClient
    ) -> None:
        conn = _mock_conn(
            fetchval_side=[None],  # nothing was set
            fetchrow_side=[_match_row()],
        )
        with _patch_db(conn):
            res = _post(client, {"interest_level": None})

        assert res.status_code == 200, res.text
        assert res.json()["interest_level"] is None
        # No state change → no event row.
        assert "interest_set" not in _executed_sql(conn)

    def test_omitted_body_field_treated_as_clear(self, client: TestClient) -> None:
        conn = _mock_conn(
            fetchval_side=["applied"],
            fetchrow_side=[_match_row()],
        )
        with _patch_db(conn):
            res = _post(client, {})

        assert res.status_code == 200, res.text
        assert res.json()["interest_level"] is None
        assert "DELETE FROM public.saved_jobs" in _executed_sql(conn)
