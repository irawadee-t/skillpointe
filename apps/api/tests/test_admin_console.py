"""
Admin console audit-fix tests:

  1. Queue unification — dashboard, approval queue, and career sources count
     "awaiting review" from ONE shared definition (util.review_queue), and
     careers-page draft batches with staged rows are reviewable.
  2. Hold-on-decision — broken/blocked-link rows default to an explicit
     'held' state on approve (never a silent skip); an explicit per-row
     approve overrides; partial messaging is keyed on held+rejected.
  3. Reject-note enforcement — server-side 422 without a meaningful note.
  4. Audit reader — GET /admin/audit-logs shape + filters.
  5. Per-source admin rate limit — pulls are keyed per source, not per user.

Everything runs offline against scripted asyncpg stand-ins.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.util.review_queue import (
    AWAITING_IMPORT_REVIEW_WHERE,
    STAGED_FROM_CAREERS_WHERE,
    batch_review_state,
    count_awaiting_import_review,
)

NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)

BATCH_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
EMP_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
CREATED_BY = "cccccccc-cccc-cccc-cccc-cccccccccccc"
ROW_OK = "11111111-1111-1111-1111-111111111111"
ROW_BROKEN = "22222222-2222-2222-2222-222222222222"


def _admin_client():
    from app.auth.dependencies import get_current_user, require_admin
    from app.auth.schemas import CurrentUser
    from app.main import app

    admin = CurrentUser(
        user_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
        email="admin@test.com", role="admin", onboarding_complete=True,
    )
    app.dependency_overrides[require_admin] = lambda: admin
    # The per-source rate-limit dependency resolves the caller itself.
    app.dependency_overrides[get_current_user] = lambda: admin
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _batch_record(status="pending", from_career_source=False):
    return {
        "id": BATCH_ID, "employer_id": EMP_ID, "created_by": CREATED_BY,
        "emp_name": "Ford", "source": "url", "source_label": "https://ford.example/careers",
        "platform": "workday", "status": status,
        "rows_total": 2, "rows_approved": 0, "rows_rejected": 0,
        "submitted_at": NOW if status == "pending" else None,
        "reviewed_at": None, "reviewer_note": None,
        "created_at": NOW, "updated_at": NOW, "published_at": None,
        "reviewer_id": None,
        "from_career_source": from_career_source,
        "rows_staged": 2, "rows_held": 0,
    }


def _import_row(row_id, link_status="ok"):
    return {
        "id": row_id, "batch_id": BATCH_ID, "status": "staged",
        "title_raw": "Welder I", "description_raw": "Weld things",
        "requirements_raw": None, "preferred_qualifications_raw": None,
        "responsibilities_raw": None, "city": "Atlanta", "state": "GA",
        "country": "US", "work_setting": None, "travel_requirement": None,
        "pay_min": None, "pay_max": None, "pay_type": None, "pay_raw": None,
        "experience_level": None, "canonical_job_family_id": None,
        "employment_type": None, "req_id": None,
        "source_url": f"https://ford.example/jobs/{row_id[:4]}",
        "job_category": None, "link_status": link_status,
        "link_checked_at": None, "posted_date": None, "created_at": NOW,
        "updated_at": NOW,
    }


class ScriptedConn:
    """Asyncpg stand-in that records every statement and routes by substring."""

    def __init__(self, batch, rows):
        self.batch = dict(batch)
        self.rows = [dict(r) for r in rows]
        self.executed: list[tuple[str, tuple]] = []
        self.row_status: dict[str, str] = {r["id"]: r["status"] for r in rows}

    async def fetchrow(self, sql, *args):
        self.executed.append((sql, args))
        if "AS batches" in sql:   # shared awaiting-review count
            return {"batches": 1, "rows": 2}
        if "FROM public.job_import_batches" in sql:
            return self.batch
        return None

    async def fetch(self, sql, *args):
        self.executed.append((sql, args))
        if "FROM public.job_import_rows" in sql and "status = 'staged'" in sql:
            return [r for r in self.rows if self.row_status[r["id"]] == "staged"]
        return []

    async def fetchval(self, sql, *args):
        self.executed.append((sql, args))
        if "INSERT INTO public.jobs" in sql:
            return "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
        if "SELECT name FROM public.employers" in sql:
            return "Ford"
        return None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        if "UPDATE public.job_import_rows SET status = 'rejected'" in sql and args:
            if "batch_id" in sql:
                for rid, st in self.row_status.items():
                    if st == "staged":
                        self.row_status[rid] = "rejected"
                return "UPDATE 2"
            self.row_status[str(args[0])] = "rejected"
        if "UPDATE public.job_import_rows SET status = 'held'" in sql and args:
            self.row_status[str(args[0])] = "held"
        if "UPDATE public.job_import_rows SET status = 'published'" in sql and args:
            self.row_status[str(args[0])] = "published"
        if "UPDATE public.job_import_batches SET status = 'rejected'" in sql:
            self.batch["status"] = "rejected"
        elif "UPDATE public.job_import_batches SET status" in sql:
            self.batch["status"] = args[1]
        return "UPDATE 1"

    def sql_containing(self, needle):
        return [s for s, _ in self.executed if needle in s]


def _db_ctx(conn):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


# ---------------------------------------------------------------------------
# 1. Queue unification — one shared definition
# ---------------------------------------------------------------------------

class TestQueueUnification:
    def test_queue_default_filter_is_the_shared_definition(self):
        from app.routers import job_imports
        assert job_imports._ADMIN_LIST_FILTERS["awaiting"] is AWAITING_IMPORT_REVIEW_WHERE
        assert job_imports._ADMIN_LIST_FILTERS["staged"] is STAGED_FROM_CAREERS_WHERE
        # "All" really is all — no hidden statuses.
        assert job_imports._ADMIN_LIST_FILTERS["all"] == "TRUE"
        for status in ("draft", "pending", "approved", "rejected", "published"):
            assert status in job_imports._ADMIN_LIST_FILTERS

    def test_dashboard_counts_via_shared_definition(self):
        from app.routers import admin
        src = inspect.getsource(admin.platform_overview) if hasattr(admin, "platform_overview") \
            else inspect.getsource(admin)
        assert "count_awaiting_import_review" in src

    async def test_count_awaiting_import_review_parses(self):
        conn = SimpleNamespace()
        async def fetchrow(sql, *a):
            assert AWAITING_IMPORT_REVIEW_WHERE in sql
            return {"batches": 3, "rows": 17}
        conn.fetchrow = fetchrow
        out = await count_awaiting_import_review(conn)
        assert out == {"batches": 3, "rows": 17}

    def test_review_state_never_silently_draft_for_careers_pulls(self):
        assert batch_review_state("pending", False, 0) == "awaiting_review"
        assert batch_review_state("draft", True, 5) == "staged_from_careers"
        assert batch_review_state("draft", True, 0) == "draft"     # nothing staged
        assert batch_review_state("draft", False, 5) == "draft"    # employer editing
        assert batch_review_state("published", True, 0) == "published"

    def test_awaiting_list_uses_shared_where(self):
        client = _admin_client()
        conn = ScriptedConn(_batch_record(), [])
        with patch("app.routers.job_imports.get_db", return_value=_db_ctx(conn)):
            resp = client.get("/admin/job-imports")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body) >= {"items", "total", "limit", "offset", "awaiting"}
        list_sql = [s for s, _ in conn.executed if "ORDER BY" in s][0]
        assert AWAITING_IMPORT_REVIEW_WHERE in list_sql

    def test_unknown_filter_is_rejected(self):
        client = _admin_client()
        resp = client.get("/admin/job-imports?status_filter=bogus")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. Hold-on-decision
# ---------------------------------------------------------------------------

class TestHoldOnDecision:
    def _approve(self, conn, payload):
        client = _admin_client()
        with patch("app.routers.job_imports.get_db", return_value=_db_ctx(conn)):
            return client.post(f"/admin/job-imports/{BATCH_ID}/approve", json=payload)

    def test_broken_link_row_defaults_to_held(self):
        conn = ScriptedConn(_batch_record(), [
            _import_row(ROW_OK, "ok"), _import_row(ROW_BROKEN, "broken"),
        ])
        resp = self._approve(conn, {})
        assert resp.status_code == 200, resp.text
        assert conn.row_status[ROW_OK] == "published"
        # Explicit, visible held state — not left silently 'staged'.
        assert conn.row_status[ROW_BROKEN] == "held"
        # Partial outcome messaging keyed on held (not only rejected).
        notify_sql = [(s, a) for s, a in conn.executed
                      if "INSERT INTO public.notifications" in s]
        assert notify_sql, "employer must be notified"
        _, args = notify_sql[0]
        assert "job_import_partial" in args
        assert any("held" in str(a) for a in args)
        # Batch is 'approved' (partial), not 'published'.
        assert conn.batch["status"] == "approved"

    def test_explicit_approve_overrides_broken_link(self):
        conn = ScriptedConn(_batch_record(), [_import_row(ROW_BROKEN, "broken")])
        resp = self._approve(conn, {"row_decisions": {ROW_BROKEN: "approve"}})
        assert resp.status_code == 200, resp.text
        assert conn.row_status[ROW_BROKEN] == "published"
        assert conn.batch["status"] == "published"

    def test_explicit_hold_decision_holds_ok_rows_too(self):
        conn = ScriptedConn(_batch_record(), [_import_row(ROW_OK, "ok")])
        resp = self._approve(conn, {"row_decisions": {ROW_OK: "hold"}})
        assert resp.status_code == 200, resp.text
        assert conn.row_status[ROW_OK] == "held"

    def test_invalid_decision_rejected(self):
        conn = ScriptedConn(_batch_record(), [_import_row(ROW_OK)])
        resp = self._approve(conn, {"row_decisions": {ROW_OK: "maybe"}})
        assert resp.status_code == 422

    def test_careers_draft_batch_is_reviewable_and_stays_draft(self):
        conn = ScriptedConn(_batch_record(status="draft", from_career_source=True),
                            [_import_row(ROW_OK, "ok")])
        resp = self._approve(conn, {})
        assert resp.status_code == 200, resp.text
        assert conn.row_status[ROW_OK] == "published"
        # Rolling careers batch keeps living as draft; the queue drops it
        # because no staged rows remain.
        assert conn.batch["status"] == "draft"

    def test_plain_employer_draft_not_approvable(self):
        conn = ScriptedConn(_batch_record(status="draft", from_career_source=False),
                            [_import_row(ROW_OK)])
        resp = self._approve(conn, {})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Reject-note enforcement
# ---------------------------------------------------------------------------

class TestRejectNote:
    def test_reject_without_note_is_422(self):
        client = _admin_client()
        resp = client.post(f"/admin/job-imports/{BATCH_ID}/reject", json={})
        assert resp.status_code == 422

    def test_reject_with_trivial_note_is_422(self):
        client = _admin_client()
        resp = client.post(f"/admin/job-imports/{BATCH_ID}/reject", json={"note": "no"})
        assert resp.status_code == 422

    def test_reject_schema_has_no_row_decisions(self):
        from app.routers.job_imports import RejectIn
        assert "row_decisions" not in RejectIn.model_fields

    def test_reject_with_note_succeeds(self):
        client = _admin_client()
        conn = ScriptedConn(_batch_record(), [])
        with patch("app.routers.job_imports.get_db", return_value=_db_ctx(conn)):
            resp = client.post(f"/admin/job-imports/{BATCH_ID}/reject",
                               json={"note": "Duplicate postings — remove rows 2-4."})
        assert resp.status_code == 200, resp.text
        assert conn.batch["status"] == "rejected"
        # Audited.
        assert conn.sql_containing("INSERT INTO public.audit_logs")


# ---------------------------------------------------------------------------
# 4. Audit reader
# ---------------------------------------------------------------------------

class TestAuditReader:
    def _conn(self):
        conn = SimpleNamespace()
        conn.queries = []

        async def fetch(sql, *args):
            conn.queries.append((sql, args))
            if "DISTINCT action" in sql:
                return [{"action": "job_import_approved"}]
            if "DISTINCT entity_type" in sql:
                return [{"entity_type": "job_import_batches"}]
            return [{
                "id": "f0f0f0f0-0000-0000-0000-000000000001",
                "actor_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                "actor_role": "admin", "action": "job_import_approved",
                "entity_type": "job_import_batches", "entity_id": BATCH_ID,
                "metadata": {"note": "looks good"}, "created_at": NOW,
                "_total": 42,
            }]
        conn.fetch = fetch
        return conn

    def test_reader_shape_and_pagination(self):
        client = _admin_client()
        conn = self._conn()
        with patch("app.routers.admin_review.get_db", return_value=_db_ctx(conn)):
            resp = client.get("/admin/audit-logs?limit=25&offset=0")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 42
        assert body["limit"] == 25
        assert body["items"][0]["action"] == "job_import_approved"
        assert body["items"][0]["note"] == "looks good"
        assert body["actions"] == ["job_import_approved"]

    def test_filters_reach_sql(self):
        client = _admin_client()
        conn = self._conn()
        with patch("app.routers.admin_review.get_db", return_value=_db_ctx(conn)):
            resp = client.get(
                "/admin/audit-logs?action=job_import_approved"
                "&entity_type=job_import_batches&date_from=2026-08-01&date_to=2026-08-02"
            )
        assert resp.status_code == 200
        main_sql, params = conn.queries[0]
        assert "a.action = $1" in main_sql
        assert "a.entity_type = $2" in main_sql
        assert "created_at >= $3::date" in main_sql
        assert "job_import_approved" in params


# ---------------------------------------------------------------------------
# 5. Per-source admin rate limit
# ---------------------------------------------------------------------------

class TestAdminPullRateLimit:
    SOURCE_A = "12121212-1212-1212-1212-121212121212"
    SOURCE_B = "34343434-3434-3434-3434-343434343434"

    def test_admin_pull_keyed_per_source_not_per_user(self):
        client = _admin_client()
        seen_keys = []

        limiter = MagicMock()

        def check(key, tier):
            seen_keys.append(key)
            # Source A is on cooldown; source B is fresh.
            allowed = self.SOURCE_A not in key
            return SimpleNamespace(allowed=allowed, reset_seconds=120)
        limiter.check = check

        run = AsyncMock(return_value={
            "pull_id": None, "batch_id": None, "status": "ok", "platform": None,
            "error": None, "jobs_found": 0, "jobs_new": 0, "jobs_updated": 0,
            "jobs_removed": 0, "jobs_rejected": 0, "links_broken": 0,
            "sync_mode": "full", "duration_ms": 1, "fetch_count": 0, "details": {},
        })
        conn = SimpleNamespace()
        conn.fetchrow = AsyncMock(return_value={
            "id": self.SOURCE_B, "employer_id": EMP_ID,
            "url": "https://x.example/careers", "batch_id": None,
            "created_by": CREATED_BY, "employer_name": "Acme",
        })
        conn.execute = AsyncMock()
        with patch("app.routers.career_sources._limiter_instance", return_value=limiter), \
             patch("app.routers.career_sources.run_pull", run), \
             patch("app.routers.career_sources.get_db", return_value=_db_ctx(conn)):
            denied = client.post(f"/admin/career-sources/{self.SOURCE_A}/pull")
            allowed = client.post(f"/admin/career-sources/{self.SOURCE_B}/pull")

        assert denied.status_code == 429
        assert allowed.status_code == 200, allowed.text
        # Keys are per SOURCE — both carry the source id, neither the user id.
        assert any(self.SOURCE_A in k for k in seen_keys)
        assert any(self.SOURCE_B in k for k in seen_keys)
        assert all(":src:" in k for k in seen_keys)


# ---------------------------------------------------------------------------
# Review feed (the 6 pending guardrail flags become visible)
# ---------------------------------------------------------------------------

class TestReviewFeed:
    def test_feed_groups_and_links(self):
        client = _admin_client()
        conn = SimpleNamespace()

        async def fetch(sql, *args):
            if "review_queue_items" in sql and "GROUP BY" in sql:
                return [{"t": "chat_guardrail", "c": 6}]
            if "FROM public.review_queue_items q" in sql:
                return [{
                    "id": "a1a1a1a1-0000-0000-0000-000000000001",
                    "item_type": "chat_guardrail", "entity_type": "chat_message",
                    "entity_id": "b2b2b2b2-0000-0000-0000-000000000002",
                    "description": "Guardrail tripped: fabricated pay claim",
                    "flags": None, "confidence_level": None, "priority": 2,
                    "status": "pending", "created_at": NOW, "resolved_at": None,
                    "resolution_action": None, "resolution_notes": None,
                    "_total": 6,
                }]
            return []
        conn.fetch = fetch
        with patch("app.routers.admin_review.get_db", return_value=_db_ctx(conn)):
            resp = client.get("/admin/review")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["pending_by_type"] == {"chat_guardrail": 6}
        assert body["pending_total"] == 6
        assert body["items"][0]["item_type"] == "chat_guardrail"

    def test_resolve_is_audited(self):
        client = _admin_client()
        conn = SimpleNamespace()
        conn.audits = []
        item_id = "a1a1a1a1-0000-0000-0000-000000000001"

        async def fetchrow(sql, *args):
            if "UPDATE public.review_queue_items" in sql:
                return {
                    "id": item_id, "item_type": "chat_guardrail",
                    "entity_type": "chat_message",
                    "entity_id": "b2b2b2b2-0000-0000-0000-000000000002",
                    "description": None, "flags": None, "confidence_level": None,
                    "priority": 2, "status": "dismissed", "created_at": NOW,
                    "resolved_at": NOW, "resolution_action": "dismissed",
                    "resolution_notes": "false positive",
                }
            return {"id": item_id, "item_type": "chat_guardrail", "status": "pending"}

        async def execute(sql, *args):
            if "audit_logs" in sql:
                conn.audits.append((sql, args))
        conn.fetchrow = fetchrow
        conn.execute = execute
        with patch("app.routers.admin_review.get_db", return_value=_db_ctx(conn)):
            resp = client.post(f"/admin/review/{item_id}/resolve",
                               json={"action": "dismissed", "note": "false positive"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "dismissed"
        assert conn.audits, "resolve must write audit_logs"
