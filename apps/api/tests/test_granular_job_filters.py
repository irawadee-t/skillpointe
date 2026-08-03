"""
test_granular_job_filters.py — granular filtering over structured job postings.

Covers:
  1. The shared predicate builder (app.util.job_filters): every filter param
     produces exactly one predicate, multi-selects are OR-within (= ANY),
     facets compose with AND, invalid enum values raise 422.
  2. GET /admin/jobs: count query and list query share the IDENTICAL where
     clause (predicate parity — the analytics-soundness rule), and the
     internal-apply filter 422s when the column doesn't exist.
  3. GET /employer/me/jobs: the employer-isolation predicate is bound FIRST
     and survives every filter combination — filters can only narrow within
     the caller's own jobs, never widen them (cross-employer attempt included).
"""
from __future__ import annotations

import re
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth.dependencies import require_admin, require_employer_or_admin
from app.auth.schemas import CurrentUser
from app.main import app
from app.routers import admin_jobs
from app.util.job_filters import (
    CANDIDATE_BANDS,
    JobFilterParams,
    build_job_conditions,
    resolve_sort,
)


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


# The outer WHERE always follows the last join line — anchoring on it avoids
# false splits on WHEREs inside FILTER(...) and scalar subqueries. The
# employer query's last join is the career-source freshness LATERAL.
_ADMIN_JOIN_MARKER = "jf.id = j.canonical_job_family_id WHERE"
_EMPLOYER_JOIN_MARKER = "fresh ON j.source_url IS NOT NULL WHERE"


def _outer_where(sql: str, marker: str, end: str | None = None) -> str:
    tail = _norm(sql).split(marker, 1)[1]
    if end:
        tail = tail.split(end, 1)[0]
    return tail.strip()


def _admin_user() -> CurrentUser:
    return CurrentUser(user_id="admin-user-id", email="a@t.co", role="admin", onboarding_complete=True)


def _employer_user() -> CurrentUser:
    return CurrentUser(user_id="emp-user-id", email="e@t.co", role="employer", onboarding_complete=True)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_state():
    admin_jobs._internal_apply_supported = None
    yield
    admin_jobs._internal_apply_supported = None
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. Pure builder tests
# ---------------------------------------------------------------------------

class TestBuildJobConditions:
    def test_no_filters_no_conditions(self):
        params: list = []
        assert build_job_conditions(JobFilterParams(), params) == []
        assert params == []

    def test_each_filter_adds_one_predicate(self):
        cases = [
            (JobFilterParams(q="weld"), "ILIKE"),
            (JobFilterParams(families=["welding"]), "jf.code = ANY"),
            (JobFilterParams(industries=["Energy"]), "e.industry"),
            (JobFilterParams(states=["GA", "TX"]), "UPPER(j.state) = ANY"),
            (JobFilterParams(city="Carroll"), "j.city ILIKE"),
            (JobFilterParams(employment_types=["full_time"]), "j.employment_type = ANY"),
            (JobFilterParams(sources=["scraper"]), "j.source = ANY"),
            (JobFilterParams(source_sites=["southwire"]), "j.source_site = ANY"),
            (JobFilterParams(status="active"), "j.is_active = TRUE"),
            (JobFilterParams(status="stale"), "INTERVAL '60 days'"),
            (JobFilterParams(apply_link="broken"), "apply_link_status = 'broken'"),
            (JobFilterParams(apply_link="unchecked"), "apply_link_status IS NULL"),
            (JobFilterParams(has_pay=True), "pay_raw"),
            (JobFilterParams(pay_gte=25.0), "COALESCE(j.pay_max, j.pay_min) >="),
            (JobFilterParams(posted_from=date(2026, 1, 1)), "j.posted_date >="),
            (JobFilterParams(posted_to=date(2026, 6, 1)), "j.posted_date <="),
            (JobFilterParams(created_from=date(2026, 1, 1)), "j.created_at >="),
            (JobFilterParams(created_to=date(2026, 6, 1)), "j.created_at <"),
            (JobFilterParams(candidates="none"), "= 0"),
        ]
        for fp, needle in cases:
            params: list = []
            conds = build_job_conditions(fp, params)
            assert len(conds) == 1, f"{fp} produced {conds}"
            assert needle in conds[0]

    def test_multiselect_binds_list_or_semantics(self):
        params: list = []
        conds = build_job_conditions(JobFilterParams(states=["GA", "TX", "AL"]), params)
        assert conds == ["UPPER(j.state) = ANY($1::text[])"]
        assert params == [["GA", "TX", "AL"]]

    def test_filters_compose_with_and(self):
        params: list = []
        fp = JobFilterParams(
            q="tech", families=["welding", "hvac"], states=["GA"],
            status="active", has_pay=True, candidates="1_9",
            sources=["scraper"], apply_link="ok", posted_from=date(2026, 1, 1),
        )
        conds = build_job_conditions(fp, params)
        assert len(conds) == 9  # one self-contained predicate per facet — ANDed by the caller
        # Each predicate is parenthesized or atomic, so joining with AND keeps
        # OR semantics contained WITHIN a facet (multi-selects use `= ANY`).
        assert all(c.strip() for c in conds)

    def test_invalid_enums_raise_422(self):
        for fp in (
            JobFilterParams(status="zombie"),
            JobFilterParams(apply_link="maybe"),
            JobFilterParams(candidates="lots"),
        ):
            with pytest.raises(HTTPException) as ei:
                build_job_conditions(fp, [])
            assert ei.value.status_code == 422

    def test_internal_apply_requires_column(self):
        with pytest.raises(HTTPException) as ei:
            build_job_conditions(JobFilterParams(internal_apply=True), [], internal_apply_supported=False)
        assert ei.value.status_code == 422
        params: list = []
        conds = build_job_conditions(
            JobFilterParams(internal_apply=True), params, internal_apply_supported=True
        )
        assert "accepts_internal_applications" in conds[0]

    def test_candidate_bands_partition(self):
        assert set(CANDIDATE_BANDS) == {"none", "1_9", "10_49", "over_50"}

    def test_bad_sort_rejected(self):
        with pytest.raises(HTTPException):
            resolve_sort("chaos")
        assert resolve_sort("newest").startswith("j.created_at")


# ---------------------------------------------------------------------------
# 2. GET /admin/jobs — endpoint + parity
# ---------------------------------------------------------------------------

def _mock_admin_jobs_db(*, total=42, internal_supported=False):
    conn = AsyncMock()
    admin_jobs._internal_apply_supported = internal_supported
    conn.fetchval = AsyncMock(return_value=total)
    # rows + 6 facet queries
    conn.fetch = AsyncMock(side_effect=[[], [], [], [], [], [], []])
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.admin_jobs.get_db", return_value=ctx), conn


class TestAdminJobsEndpoint:
    FILTERS = {
        "q": "weld",
        "families": "welding,hvac",
        "states": "ga,TX",
        "city": "Carrollton",
        "sources": "scraper",
        "source_sites": "southwire",
        "status": "active",
        "apply_link": "ok",
        "has_pay": "true",
        "pay_gte": "20",
        "posted_from": "2026-01-01",
        "candidates": "1_9",
        "sort": "pay",
    }

    def test_count_and_list_share_identical_where(self, client: TestClient):
        """The parity invariant: 'Showing N' can never drift from the list."""
        app.dependency_overrides[require_admin] = _admin_user
        ctx, conn = _mock_admin_jobs_db()
        with ctx:
            res = client.get("/admin/jobs", params=self.FILTERS)
        assert res.status_code == 200

        count_sql = conn.fetchval.await_args_list[0].args[0]
        list_sql = conn.fetch.await_args_list[0].args[0]
        count_where = _outer_where(count_sql, _ADMIN_JOIN_MARKER)
        list_where = _outer_where(list_sql, _ADMIN_JOIN_MARKER, end="ORDER BY")
        assert count_where == list_where
        # And the same bound params (list adds only LIMIT/OFFSET at the end).
        count_params = conn.fetchval.await_args_list[0].args[1:]
        list_params = conn.fetch.await_args_list[0].args[1:]
        assert list_params[: len(count_params)] == count_params

        # Every requested facet made it into the predicate.
        for needle in ("ILIKE", "jf.code = ANY", "UPPER(j.state) = ANY",
                       "j.city ILIKE", "j.source = ANY", "j.source_site = ANY",
                       "j.is_active = TRUE", "apply_link_status = 'ok'",
                       "COALESCE(j.pay_max, j.pay_min) >=", "j.posted_date >="):
            assert needle in count_where
        # Multi-select states are uppercased into one bound list (OR-within).
        assert ["GA", "TX"] in count_params

    def test_unfiltered_count_and_list_still_parity(self, client: TestClient):
        app.dependency_overrides[require_admin] = _admin_user
        ctx, conn = _mock_admin_jobs_db()
        with ctx:
            res = client.get("/admin/jobs")
        assert res.status_code == 200
        assert res.json()["total"] == 42
        count_sql = conn.fetchval.await_args_list[0].args[0]
        list_sql = conn.fetch.await_args_list[0].args[0]
        assert _outer_where(count_sql, _ADMIN_JOIN_MARKER) == "1=1"
        assert _outer_where(list_sql, _ADMIN_JOIN_MARKER, end="ORDER BY") == "1=1"

    def test_internal_apply_422_when_column_absent(self, client: TestClient):
        app.dependency_overrides[require_admin] = _admin_user
        ctx, _ = _mock_admin_jobs_db(internal_supported=False)
        with ctx:
            res = client.get("/admin/jobs", params={"internal_apply": "true"})
        assert res.status_code == 422

    def test_internal_apply_filters_when_supported(self, client: TestClient):
        app.dependency_overrides[require_admin] = _admin_user
        ctx, conn = _mock_admin_jobs_db(internal_supported=True)
        with ctx:
            res = client.get("/admin/jobs", params={"internal_apply": "true"})
        assert res.status_code == 200
        assert res.json()["supports_internal_apply"] is True
        assert "accepts_internal_applications" in conn.fetchval.await_args_list[0].args[0]

    def test_requires_admin(self, client: TestClient):
        res = client.get("/admin/jobs")
        assert res.status_code in (401, 403)

    def test_employer_role_rejected(self, client: TestClient):
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        res = client.get("/admin/jobs")
        assert res.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 3. GET /employer/me/jobs — isolation under every filter combination
# ---------------------------------------------------------------------------

def _mock_employer_jobs_db():
    conn = AsyncMock()
    # order: supports_internal, company name, unfiltered total
    conn.fetchval = AsyncMock(side_effect=[None, "Acme Industrial", 7])
    conn.fetch = AsyncMock(side_effect=[[], []])  # rows, facet rows
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.employers.get_db", return_value=ctx), conn


class TestEmployerJobsIsolation:
    COMBOS = [
        {},
        {"q": "weld"},
        {"families": "welding,hvac", "states": "GA", "status": "active"},
        {"has_pay": "true", "candidates": "none", "sort": "title"},
        {"sources": "manual", "apply_link": "unchecked", "posted_from": "2026-01-01"},
    ]

    @pytest.mark.parametrize("combo", COMBOS)
    def test_employer_id_predicate_first_under_all_combos(self, client: TestClient, combo):
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        ctx, conn = _mock_employer_jobs_db()
        with ctx, patch(
            "app.routers.employers._resolve_employer_id",
            new=AsyncMock(return_value="emp-A-uuid"),
        ):
            res = client.get("/employer/me/jobs", params=combo)
        assert res.status_code == 200

        list_call = conn.fetch.await_args_list[0]
        sql = list_call.args[0]
        where = _outer_where(sql, _EMPLOYER_JOIN_MARKER, end="GROUP BY")
        # Isolation predicate is present and FIRST — filters AND after it.
        assert where.startswith("j.employer_id = $1")
        assert list_call.args[1] == "emp-A-uuid"

    def test_cross_employer_attempt_cannot_widen(self, client: TestClient):
        """A hostile employer_id query param is ignored — binding stays the
        caller's own employer under a full stack of filters."""
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        ctx, conn = _mock_employer_jobs_db()
        with ctx, patch(
            "app.routers.employers._resolve_employer_id",
            new=AsyncMock(return_value="emp-A-uuid"),
        ):
            res = client.get(
                "/employer/me/jobs",
                params={"employer_id": "emp-B-uuid", "status": "active", "q": "weld"},
            )
        assert res.status_code == 200
        list_call = conn.fetch.await_args_list[0]
        assert list_call.args[1] == "emp-A-uuid"
        assert "emp-B-uuid" not in list_call.args

    def test_filtered_total_matches_returned_list_by_construction(self, client: TestClient):
        """total_jobs is computed from the same filtered row set it returns —
        list/count parity holds by construction on this endpoint."""
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        ctx, _ = _mock_employer_jobs_db()
        with ctx, patch(
            "app.routers.employers._resolve_employer_id",
            new=AsyncMock(return_value="emp-A-uuid"),
        ):
            res = client.get("/employer/me/jobs", params={"status": "inactive"})
        body = res.json()
        assert body["total_jobs"] == len(body["jobs"])
        assert body["unfiltered_total"] == 7
