"""
test_suggest_endpoints.py — the shared prefix-suggest layer + its endpoints.

Covers:
  1. app.util.suggest.fetch_label_suggestions — SQL shape: substring WHERE,
     prefix-first ORDER BY, bound limit; narrowing patterns per keystroke
     (g → ge → gev).
  2. cap_groups — total ≤ 8, every non-empty group keeps a row.
  3. GET /admin/jobs/suggest — grouped job titles + employer names; admin-only.
  4. GET /employer/me/verified-workers/suggest — credential + trade names,
     every query carrying the consent/verified/adult gate (role isolation);
     employer-or-admin only; never captured by /{applicant_id}.
  5. GET /jobs/suggest — active-jobs-only predicate parity with /jobs/browse.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import (
    require_admin,
    require_authenticated,
    require_employer_or_admin,
)
from app.auth.schemas import CurrentUser
from app.main import app
from app.util.suggest import Suggestion, cap_groups, fetch_label_suggestions


def _user(role: str) -> CurrentUser:
    return CurrentUser(
        user_id=f"{role}-user-id",
        email=f"{role}@test.com",
        role=role,
        onboarding_complete=True,
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _mock_db(module: str, fetch_side_effect):
    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=fetch_side_effect)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch(f"{module}.get_db", return_value=ctx), conn


# ---------------------------------------------------------------------------
# 1. The shared helper
# ---------------------------------------------------------------------------

class TestFetchLabelSuggestions:
    def _run(self, q: str, rows):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=rows)
        out = asyncio.run(fetch_label_suggestions(
            conn,
            kind="employer",
            label_expr="e.name",
            from_clause="FROM public.employers e",
            q=q,
            limit=8,
        ))
        return out, conn

    def test_binds_substring_prefix_and_limit(self):
        out, conn = self._run("ge", [{"label": "GE Vernova"}])
        sql = conn.fetch.await_args.args[0]
        args = conn.fetch.await_args.args[1:]
        assert args == ("%ge%", "ge%", 8)
        # Substring match filters; prefix match ranks first.
        assert "ILIKE $1" in sql
        assert "ORDER BY (e.name ILIKE $2) DESC" in sql
        assert "LIMIT $3" in sql
        assert [s.label for s in out] == ["GE Vernova"]
        assert out[0].kind == "employer"

    def test_patterns_narrow_per_keystroke(self):
        """g → ge → gev: each keystroke re-binds a tighter pattern."""
        seen = []
        for q in ("g", "ge", "gev"):
            _, conn = self._run(q, [])
            seen.append(conn.fetch.await_args.args[1:3])
        assert seen == [("%g%", "g%"), ("%ge%", "ge%"), ("%gev%", "gev%")]

    def test_blank_query_short_circuits(self):
        conn = AsyncMock()
        out = asyncio.run(fetch_label_suggestions(
            conn, kind="job", label_expr="x", from_clause="FROM t", q="   ", limit=8,
        ))
        assert out == []
        conn.fetch.assert_not_awaited()

    def test_null_and_blank_labels_dropped(self):
        out, _ = self._run("g", [{"label": None}, {"label": "  "}, {"label": "GE"}])
        assert [s.label for s in out] == ["GE"]


class TestCapGroups:
    def _g(self, kind: str, n: int) -> list[Suggestion]:
        return [Suggestion(kind=kind, label=f"{kind}-{i}") for i in range(n)]

    def test_total_capped_at_eight(self):
        merged = cap_groups([self._g("job", 8), self._g("employer", 8)])
        assert len(merged) == 8

    def test_every_nonempty_group_survives(self):
        merged = cap_groups([self._g("job", 8), self._g("employer", 1)])
        kinds = {s.kind for s in merged}
        assert kinds == {"job", "employer"}

    def test_empty_groups_ignored(self):
        assert cap_groups([[], []]) == []
        merged = cap_groups([[], self._g("trade", 2)])
        assert [s.kind for s in merged] == ["trade", "trade"]


# ---------------------------------------------------------------------------
# 3. Admin jobs console suggest
# ---------------------------------------------------------------------------

class TestAdminJobsSuggest:
    def test_grouped_titles_then_employers(self, client: TestClient):
        app.dependency_overrides[require_admin] = lambda: _user("admin")
        ctx, conn = _mock_db(
            "app.routers.admin_jobs",
            [
                [{"label": "Generator Technician"}],
                [{"label": "GE Vernova"}, {"label": "General Mills"}],
            ],
        )
        with ctx:
            res = client.get("/admin/jobs/suggest", params={"q": "ge"})
        assert res.status_code == 200
        rows = res.json()["suggestions"]
        assert [(r["kind"], r["label"]) for r in rows] == [
            ("job", "Generator Technician"),
            ("employer", "GE Vernova"),
            ("employer", "General Mills"),
        ]
        # Both queries bind the substring + prefix patterns for "ge".
        for call in conn.fetch.await_args_list:
            assert "%ge%" in call.args and "ge%" in call.args

    def test_requires_admin(self, client: TestClient):
        res = client.get("/admin/jobs/suggest", params={"q": "ge"})
        assert res.status_code in (401, 403)

    def test_missing_q_rejected(self, client: TestClient):
        app.dependency_overrides[require_admin] = lambda: _user("admin")
        assert client.get("/admin/jobs/suggest").status_code == 422


# ---------------------------------------------------------------------------
# 4. Verified-worker keyword suggest — consent isolation
# ---------------------------------------------------------------------------

class TestVerifiedWorkersSuggest:
    def test_credentials_and_trades(self, client: TestClient):
        app.dependency_overrides[require_employer_or_admin] = lambda: _user("employer")
        ctx, conn = _mock_db(
            "app.routers.verified_workers",
            [[{"label": "EPA 608"}], [{"label": "Electrical"}]],
        )
        with ctx:
            res = client.get("/employer/me/verified-workers/suggest", params={"q": "e"})
        assert res.status_code == 200
        rows = res.json()["suggestions"]
        assert [(r["kind"], r["label"]) for r in rows] == [
            ("credential", "EPA 608"),
            ("trade", "Electrical"),
        ]

    def test_every_source_query_carries_the_consent_gate(self, client: TestClient):
        """Isolation: suggestions may only be drawn from workers who consented
        to employer sharing, hold a verified credential, and are adults —
        the same _DISCOVERABLE gate the search list enforces."""
        app.dependency_overrides[require_employer_or_admin] = lambda: _user("employer")
        ctx, conn = _mock_db("app.routers.verified_workers", [[], []])
        with ctx:
            res = client.get("/employer/me/verified-workers/suggest", params={"q": "weld"})
        assert res.status_code == 200
        assert len(conn.fetch.await_args_list) == 2
        for call in conn.fetch.await_args_list:
            sql = call.args[0]
            assert "consent_settings" in sql
            assert "external_sharing ? 'employer'" in sql
            assert "verification_level >=" in sql
            assert "date_of_birth" in sql  # adult gate

    def test_not_captured_by_applicant_id_route(self, client: TestClient):
        """/suggest must resolve to the suggest endpoint, not 404/422 from
        the /{applicant_id} verify route."""
        app.dependency_overrides[require_employer_or_admin] = lambda: _user("employer")
        ctx, _ = _mock_db("app.routers.verified_workers", [[], []])
        with ctx:
            res = client.get("/employer/me/verified-workers/suggest", params={"q": "x"})
        assert res.status_code == 200
        assert res.json() == {"suggestions": []}

    def test_applicant_role_rejected(self, client: TestClient):
        res = client.get("/employer/me/verified-workers/suggest", params={"q": "e"})
        assert res.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 5. Applicant browse suggest — active jobs only
# ---------------------------------------------------------------------------

class TestJobsBrowseSuggest:
    def test_grouped_and_active_only(self, client: TestClient):
        app.dependency_overrides[require_authenticated] = lambda: _user("applicant")
        ctx, conn = _mock_db(
            "app.routers.jobs",
            [
                [{"label": "Generator Technician"}],
                [{"label": "GE Vernova"}],
                [{"label": "General Maintenance"}],
            ],
        )
        with ctx:
            res = client.get("/jobs/suggest", params={"q": "ge"})
        assert res.status_code == 200
        rows = res.json()["suggestions"]
        assert [(r["kind"], r["label"]) for r in rows] == [
            ("job", "Generator Technician"),
            ("employer", "GE Vernova"),
            ("trade", "General Maintenance"),
        ]
        # Predicate parity with /jobs/browse: only active jobs feed the
        # dropdown (directly or via EXISTS on active jobs).
        for call in conn.fetch.await_args_list:
            assert "j.is_active = TRUE" in call.args[0]

    def test_requires_auth(self, client: TestClient):
        res = client.get("/jobs/suggest", params={"q": "ge"})
        assert res.status_code in (401, 403)

    def test_limit_is_bound_not_interpolated(self, client: TestClient):
        app.dependency_overrides[require_authenticated] = lambda: _user("applicant")
        ctx, conn = _mock_db("app.routers.jobs", [[], [], []])
        with ctx:
            client.get("/jobs/suggest", params={"q": "ge"})
        for call in conn.fetch.await_args_list:
            assert call.args[-1] == 8  # per-group cap, bound as a parameter
