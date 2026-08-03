"""
test_candidate_verified_event.py — pins the candidate_verified event writer.

GET /employer/me/verified-workers/{applicant_id} (SKILLED Verify) is the one
engagement writer with no local UI path to exercise (it needs a consented,
verified worker), so the admin engagement dashboards' 'candidate_verified'
metric is covered here instead: the endpoint must log exactly one
engagement_events row with the correct applicant/employer ids for employers,
and must NOT log for admins (read-only view, per the admin-cannot-act-as-
employer guardrail).

Mock-DB style, same approach as test_engagement_instrumentation.py.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.auth.dependencies import require_employer_or_admin
from app.auth.schemas import CurrentUser
from app.main import app

EMPLOYER_USER_ID = "bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb"
ADMIN_USER_ID = "cccccccc-0000-0000-0000-cccccccccccc"
APPLICANT_ID = "11111111-0000-0000-0000-111111111111"
EMPLOYER_ID = "22222222-0000-0000-0000-222222222222"

APPLICANT_ROW = {
    "id": APPLICANT_ID,
    "first_name": "Jane",
    "last_name": "Smith",
    "city": "Austin",
    "state": "TX",
    "trade": "Welding",
}


def _mock_conn() -> AsyncMock:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=APPLICANT_ROW)
    # 1st fetchval: consent external_sharing; 2nd: employer id resolution.
    conn.fetchval = AsyncMock(side_effect=[["employer"], EMPLOYER_ID])
    conn.fetch = AsyncMock(return_value=[])  # no credential rows needed
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    return conn


def _patch_db(conn: AsyncMock):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.verified_workers.get_db", return_value=ctx)


def _override(user: CurrentUser):
    app.dependency_overrides[require_employer_or_admin] = lambda: user


def _clear():
    app.dependency_overrides.pop(require_employer_or_admin, None)


def _event_inserts(conn: AsyncMock) -> list[tuple[Any, ...]]:
    return [
        c.args for c in conn.execute.await_args_list
        if "engagement_events" in c.args[0]
    ]


def test_employer_verify_logs_candidate_verified_event():
    conn = _mock_conn()
    _override(CurrentUser(
        user_id=EMPLOYER_USER_ID, email="employer@test.local",
        role="employer", onboarding_complete=True,
    ))
    try:
        with _patch_db(conn):
            res = TestClient(app).get(f"/employer/me/verified-workers/{APPLICANT_ID}")
        assert res.status_code == 200

        inserts = _event_inserts(conn)
        assert len(inserts) == 1, "exactly one candidate_verified event per verify"
        sql, *params = inserts[0]
        assert "'candidate_verified'" in sql
        # Correct actor/subject ids: applicant verified, employer acting.
        assert params[0] == APPLICANT_ID
        assert params[1] == EMPLOYER_ID
        assert params[2]["via"] == "skilled_verify"
    finally:
        _clear()


def test_admin_verify_does_not_log_event():
    """Admins viewing SKILLED Verify are read-only — no engagement event, so
    admin browsing never inflates the employer engagement dashboards."""
    conn = _mock_conn()
    conn.fetchval = AsyncMock(side_effect=[["employer"]])  # consent only
    _override(CurrentUser(
        user_id=ADMIN_USER_ID, email="admin@test.local",
        role="admin", onboarding_complete=True,
    ))
    try:
        with _patch_db(conn):
            res = TestClient(app).get(f"/employer/me/verified-workers/{APPLICANT_ID}")
        assert res.status_code == 200
        assert _event_inserts(conn) == []
    finally:
        _clear()
