"""
test_granular_worker_filters.py — verified-worker directory granular filters.

The critical invariant: filters NARROW the discoverable set, they never widen
visibility. The consent + verified-credential + adult gate (_DISCOVERABLE) must
be present in the count query AND the list query under EVERY filter
combination — an employer stacking filters can never surface a worker who
didn't consent to employer sharing.

Also covers: each new filter's predicate, multi-select trades, credential-type
taxonomy validation, availability, relocation, commute-radius reachability
(geocode mocked), and last-active recency.
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import require_employer_or_admin
from app.auth.schemas import CurrentUser
from app.main import app
from app.routers.verified_workers import _DISCOVERABLE


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


_GATE = _norm(_DISCOVERABLE)


def _employer_user() -> CurrentUser:
    return CurrentUser(user_id="emp-user-id", email="e@t.co", role="employer", onboarding_complete=True)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _mock_db(total=0):
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=total)
    conn.fetch = AsyncMock(side_effect=[[], [], []])  # rows, trade facet, cred facet
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch("app.routers.verified_workers.get_db", return_value=ctx), conn


COMBOS = [
    {},
    {"q": "welding"},
    {"trades": "welding,hvac", "state": "GA"},
    {"credential_types": "certification,safety", "min_level": "2"},
    {"available_by": "now", "relocate": "true", "active_within_days": "90"},
    {"trades": "welding", "credential_types": "license", "min_level": "1",
     "available_by": "2026-09-01", "relocate": "false", "active_within_days": "30"},
]


class TestConsentGateUnderAllFilters:
    @pytest.mark.parametrize("combo", COMBOS)
    def test_gate_present_in_count_and_list(self, client: TestClient, combo):
        """Employer isolation/consent: no filter combination removes the gate.

        (The directory is consent-scoped rather than employer-scoped: every
        employer sees the same consented pool, so 'cross-employer' widening
        means escaping the consent gate — asserted impossible here.)"""
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        ctx, conn = _mock_db()
        with ctx:
            res = client.get("/employer/me/verified-workers", params=combo)
        assert res.status_code == 200

        count_sql = _norm(conn.fetchval.await_args_list[0].args[0])
        list_sql = _norm(conn.fetch.await_args_list[0].args[0])
        assert _GATE in count_sql, f"consent gate missing from count for {combo}"
        assert _GATE in list_sql, f"consent gate missing from list for {combo}"

        # Parity: count where == list where (list adds ORDER BY/LIMIT after).
        # Both queries place the outer WHERE right after the taxonomy join.
        marker = "jf.id = a.canonical_job_family_id WHERE"
        count_where = count_sql.split(marker, 1)[1].strip()
        list_where = list_sql.split(marker, 1)[1].split("ORDER BY", 1)[0].strip()
        assert count_where == list_where


class TestNewFilterPredicates:
    def _where(self, conn) -> str:
        sql = _norm(conn.fetchval.await_args_list[0].args[0])
        return sql.split("jf.id = a.canonical_job_family_id WHERE", 1)[1]

    def test_trades_multiselect(self, client: TestClient):
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        ctx, conn = _mock_db()
        with ctx:
            client.get("/employer/me/verified-workers", params={"trades": "welding,hvac"})
        assert "jf.code = ANY" in self._where(conn)
        assert ["welding", "hvac"] in conn.fetchval.await_args_list[0].args[1:]

    def test_single_trade_back_compat(self, client: TestClient):
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        ctx, conn = _mock_db()
        with ctx:
            client.get("/employer/me/verified-workers", params={"trade": "welding"})
        assert ["welding"] in conn.fetchval.await_args_list[0].args[1:]

    def test_min_level_and_credential_type(self, client: TestClient):
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        ctx, conn = _mock_db()
        with ctx:
            client.get("/employer/me/verified-workers",
                       params={"min_level": "2", "credential_types": "safety"})
        where = self._where(conn)
        assert "cl.verification_level >= $" in where
        assert "ct.credential_type = ANY" in where

    def test_invalid_credential_type_422(self, client: TestClient):
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        ctx, _ = _mock_db()
        with ctx:
            res = client.get("/employer/me/verified-workers",
                             params={"credential_types": "certification,bogus"})
        assert res.status_code == 422

    def test_availability_and_relocate_and_recency(self, client: TestClient):
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        ctx, conn = _mock_db()
        with ctx:
            client.get("/employer/me/verified-workers",
                       params={"available_by": "now", "relocate": "true",
                               "active_within_days": "45"})
        where = self._where(conn)
        assert "a.available_from_date IS NULL OR a.available_from_date <=" in where
        assert "COALESCE(a.willing_to_relocate, FALSE) =" in where
        assert "make_interval(days =>" in where

    def test_bad_available_by_422(self, client: TestClient):
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        ctx, _ = _mock_db()
        with ctx:
            res = client.get("/employer/me/verified-workers",
                             params={"available_by": "soonish"})
        assert res.status_code == 422

    def test_commute_radius_reachable_from_city(self, client: TestClient):
        """near_city geocodes once, then filters on the WORKER's stated radius."""
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        ctx, conn = _mock_db()
        with ctx, patch(
            "app.routers.verified_workers.geocode",
            new=AsyncMock(return_value=(33.58, -85.08)),
        ) as geo:
            res = client.get("/employer/me/verified-workers",
                             params={"near_city": "Carrollton", "near_state": "GA"})
        assert res.status_code == 200
        geo.assert_awaited_once()
        where = self._where(conn)
        assert "a.lat IS NOT NULL" in where
        assert "commute_radius_miles" in where       # worker's own radius
        assert "50.0" in where                        # default radius fallback
        args = conn.fetchval.await_args_list[0].args[1:]
        assert 33.58 in args and -85.08 in args
        # The consent gate is still there with the geo filter stacked on.
        assert _GATE in _norm(conn.fetchval.await_args_list[0].args[0])

    def test_unresolvable_city_422(self, client: TestClient):
        app.dependency_overrides[require_employer_or_admin] = _employer_user
        ctx, _ = _mock_db()
        with ctx, patch(
            "app.routers.verified_workers.geocode",
            new=AsyncMock(return_value=None),
        ):
            res = client.get("/employer/me/verified-workers",
                             params={"near_city": "Atlantis"})
        assert res.status_code == 422

    def test_requires_role(self, client: TestClient):
        res = client.get("/employer/me/verified-workers")
        assert res.status_code in (401, 403)
