"""
test_granular_employer_filters.py — GET /admin/employers granular directory filters.

Covers:
  1. Each new filter param contributes its predicate; multi-selects are
     OR-within (= ANY) and facets AND together.
  2. Count/list predicate parity: the COUNT query and the page query embed
     the IDENTICAL where clause with identical bound params.
  3. Invalid enum values (jobs_band, sort) are rejected with 422.
  4. Only admins may call it.
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_admin
from app.auth.schemas import CurrentUser
from app.main import app


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _admin_user() -> CurrentUser:
    return CurrentUser(user_id="admin-user-id", email="a@t.co", role="admin", onboarding_complete=True)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _mock_db(total=11):
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=total)
    conn.fetch = AsyncMock(side_effect=[[], [], []])  # rows, industry facet, state facet
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.admin.get_db", return_value=ctx), conn


def _wheres(conn):
    """Extract the OUTER where clause from both queries.

    Anchored on the join/table markers so inner WHEREs (EXISTS subqueries,
    scalar counts) can't confuse the split.
    """
    count_sql = conn.fetchval.await_args_list[0].args[0]
    list_sql = conn.fetch.await_args_list[0].args[0]
    count_where = _norm(count_sql).split("FROM public.employers e WHERE", 1)[1].strip()
    list_where = _norm(
        _norm(list_sql).split("ON j.employer_id = e.id WHERE", 1)[1]
    ).split("GROUP BY", 1)[0].strip()
    return count_sql, list_sql, count_where, list_where


class TestAdminEmployersFilters:
    def test_full_stack_composes_and_count_list_parity(self, client: TestClient):
        app.dependency_overrides[require_admin] = _admin_user
        ctx, conn = _mock_db()
        with ctx:
            res = client.get("/admin/employers", params={
                "q": "south",
                "states": "ga,al",
                "industry": "Manufacturing,Energy",
                "is_partner": "true",
                "has_active_jobs": "true",
                "jobs_band": "11_100",
                "has_hired": "true",
                "has_outreach": "false",
                "has_career_source": "true",
                "created_from": "2026-01-01",
                "created_to": "2026-06-30",
                "sort": "recent",
            })
        assert res.status_code == 200

        _, _, count_where, list_where = _wheres(conn)
        assert count_where == list_where  # parity: one predicate, two queries

        for needle in (
            "e.name ILIKE",
            "e.state = ANY",
            "TRIM(e.industry) = ANY",
            "e.is_partner =",
            "ja.is_active = TRUE",
            "BETWEEN 11 AND 100",
            "h.outcome_type = 'hired'",
            "NOT EXISTS (SELECT 1 FROM public.employer_outreach",
            "public.employer_career_sources",
            "e.created_at >=",
            "e.created_at <",
        ):
            assert needle in count_where, f"missing predicate: {needle}"

        count_params = conn.fetchval.await_args_list[0].args[1:]
        list_params = conn.fetch.await_args_list[0].args[1:]
        assert list_params[: len(count_params)] == count_params
        assert ["GA", "AL"] in count_params            # states multi-select, uppercased
        assert ["Manufacturing", "Energy"] in count_params  # industry multi-select

        # recent sort orders by the activity expression
        assert "last_activity_at DESC NULLS LAST" in conn.fetch.await_args_list[0].args[0]

    def test_no_filters_where_is_neutral(self, client: TestClient):
        app.dependency_overrides[require_admin] = _admin_user
        ctx, conn = _mock_db()
        with ctx:
            res = client.get("/admin/employers")
        assert res.status_code == 200
        assert res.json()["total"] == 11
        _, _, count_where, list_where = _wheres(conn)
        assert count_where == list_where == "1=1"

    def test_single_state_back_compat(self, client: TestClient):
        """Old ?state=GA calls keep working, mapped into the multi-select."""
        app.dependency_overrides[require_admin] = _admin_user
        ctx, conn = _mock_db()
        with ctx:
            res = client.get("/admin/employers", params={"state": "ga"})
        assert res.status_code == 200
        assert ["GA"] in conn.fetchval.await_args_list[0].args[1:]

    def test_jobs_band_none_uses_zero_count(self, client: TestClient):
        app.dependency_overrides[require_admin] = _admin_user
        ctx, conn = _mock_db()
        with ctx:
            res = client.get("/admin/employers", params={"jobs_band": "none"})
        assert res.status_code == 200
        _, _, count_where, list_where = _wheres(conn)
        assert "= 0" in count_where and count_where == list_where

    @pytest.mark.parametrize("params", [
        {"jobs_band": "a_lot"},
        {"sort": "vibes"},
        {"created_from": "January 1st"},
    ])
    def test_invalid_values_rejected(self, client: TestClient, params):
        app.dependency_overrides[require_admin] = _admin_user
        ctx, _ = _mock_db()
        with ctx:
            res = client.get("/admin/employers", params=params)
        assert res.status_code == 422

    def test_requires_admin(self, client: TestClient):
        res = client.get("/admin/employers")
        assert res.status_code in (401, 403)
