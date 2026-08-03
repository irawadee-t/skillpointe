"""
Real-Postgres integration tests for the critical money/state flows.

Unlike the rest of the suite (which mocks the DB), these run the ACTUAL SQL
against a live Postgres, so they catch schema-level bugs the mocked tests
cannot — e.g. an audit_logs INSERT that names columns which don't exist, or a
missing/renamed unique constraint an ON CONFLICT clause depends on. A GDPR
hard-delete bug (wrong audit_logs column names) previously slipped through
precisely because nothing exercised the real schema.

How to run:
    # against the local Supabase Postgres
    python -m pytest tests/integration/ -v

Isolation strategy:
    Every test operates on ONE directly-opened asyncpg connection (not the app
    pool, to avoid pool/event-loop lifecycle friction). All writes use throwaway
    rows with freshly-generated UUIDs and are removed in an explicit `finally`
    cleanup. Deleting the throwaway auth.users row cascades to applicants and its
    child rows; throwaway employers/jobs and preserved audit_logs tombstones are
    cleaned up by id. The seeded test users are never touched.

    The module self-skips when no Postgres is reachable at DATABASE_URL, so it is
    safe to run in environments without a database (the mocked unit tests there
    still pass).
"""
from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import asyncpg
import pytest

# Mark the whole module. `integration` is registered in pyproject.toml.
pytestmark = pytest.mark.integration

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:54322/postgres"
)


async def _try_connect() -> asyncpg.Connection | None:
    try:
        return await asyncpg.connect(DATABASE_URL, timeout=5)
    except Exception:
        return None


@pytest.fixture
async def conn():
    """A live asyncpg connection to the real DB, or skip if unreachable."""
    c = await _try_connect()
    if c is None:
        pytest.skip(f"No Postgres reachable at {DATABASE_URL}")
    # Match the app's JSONB codec so jsonb columns round-trip as dict/list.
    await c.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    try:
        yield c
    finally:
        await c.close()


# ---------------------------------------------------------------------------
# Throwaway-row helpers
# ---------------------------------------------------------------------------

async def _make_user(conn, role: str = "applicant") -> str:
    """Create a throwaway auth user + user_profile; return the user_id."""
    uid = str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO auth.users (id, email) VALUES ($1, $2)",
        uid, f"itest_{uid[:8]}@test.local",
    )
    await conn.execute(
        "INSERT INTO public.user_profiles (user_id, role) VALUES ($1, $2)",
        uid, role,
    )
    return uid


async def _make_applicant(conn, user_id: str) -> str:
    aid = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO public.applicants (id, user_id, first_name, last_name)
        VALUES ($1, $2, 'Itest', 'Applicant')
        """,
        aid, user_id,
    )
    return aid


async def _make_employer(conn, name: str | None = None) -> str:
    eid = str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO public.employers (id, name) VALUES ($1, $2)",
        eid, name or f"Itest Employer {eid[:8]}",
    )
    return eid


async def _make_job(conn, employer_id: str, title: str, active: bool = True) -> str:
    jid = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO public.jobs (id, employer_id, title_raw, is_active)
        VALUES ($1, $2, $3, $4)
        """,
        jid, employer_id, title, active,
    )
    return jid


async def _cleanup(conn, *, user_ids=(), employer_ids=()):
    """Remove throwaway rows. Deleting the auth user cascades applicants + child
    rows; employers cascade their jobs/applications/hire_outcomes. audit_logs
    tombstones (preserved by design) are cleared by entity_id."""
    for uid in user_ids:
        await conn.execute("DELETE FROM public.audit_logs WHERE entity_id = $1", uid)
        await conn.execute("DELETE FROM auth.users WHERE id = $1", uid)
    for eid in employer_ids:
        await conn.execute("DELETE FROM public.employers WHERE id = $1", eid)


# ===========================================================================
# 1. Account deletion + audit trail  (the highest-value test)
# ===========================================================================

async def test_hard_delete_cascades_and_writes_audit_log(conn):
    """The real _hard_delete_user path must (a) remove the user's rows from the
    cascade tables and (b) actually write an audit_logs row named
    action='account_hard_deleted'. Because the whole delete runs in one
    transaction, a wrong audit_logs column name would raise and roll everything
    back — so asserting the tombstone exists is what catches that bug class."""
    from app.routers.account import _hard_delete_user

    user_id = await _make_user(conn, "applicant")
    applicant_id = await _make_applicant(conn, user_id)
    employer_id = await _make_employer(conn)
    job_id = await _make_job(conn, employer_id, "Itest Delete Target")

    # Child rows across a few cascade tables.
    await conn.execute(
        "INSERT INTO public.saved_jobs (applicant_id, job_id, interest_level) VALUES ($1, $2, 'interested')",
        applicant_id, job_id,
    )
    match_id = await conn.fetchval(
        "INSERT INTO public.matches (applicant_id, job_id) VALUES ($1, $2) RETURNING id",
        applicant_id, job_id,
    )
    await conn.execute(
        """
        INSERT INTO public.applications (applicant_id, job_id, employer_id, status)
        VALUES ($1, $2, $3, 'submitted')
        """,
        applicant_id, job_id, employer_id,
    )

    try:
        # Patch the Supabase admin client so the auth.users delete is a no-op
        # (no network dependency); everything else is real SQL.
        with patch("app.auth.dependencies._get_admin_client", return_value=MagicMock()):
            cleared = await _hard_delete_user(conn, user_id)

        # (a) cascade tables are empty for this user/applicant
        assert await conn.fetchval(
            "SELECT count(*) FROM public.user_profiles WHERE user_id = $1", user_id
        ) == 0
        assert await conn.fetchval(
            "SELECT count(*) FROM public.applicants WHERE id = $1", applicant_id
        ) == 0
        assert await conn.fetchval(
            "SELECT count(*) FROM public.saved_jobs WHERE applicant_id = $1", applicant_id
        ) == 0
        assert await conn.fetchval(
            "SELECT count(*) FROM public.matches WHERE id = $1", match_id
        ) == 0
        assert await conn.fetchval(
            "SELECT count(*) FROM public.applications WHERE applicant_id = $1", applicant_id
        ) == 0

        # user-keyed tables that were explicitly cleared appear in the report
        assert "user_profiles" in cleared
        assert "applicants" in cleared

        # (b) the audit tombstone was actually written with the real columns
        audit = await conn.fetchrow(
            """
            SELECT actor_id, actor_role, action, entity_type, entity_id, metadata
              FROM public.audit_logs
             WHERE action = 'account_hard_deleted' AND entity_id = $1
            """,
            user_id,
        )
        assert audit is not None, "no account_hard_deleted audit row was written"
        assert audit["actor_id"] is None            # system action
        assert audit["actor_role"] == "system"
        assert audit["entity_type"] == "user_profiles"
        assert str(audit["entity_id"]) == user_id
        # metadata is JSONB → decoded to a dict with the cleared-table list
        assert isinstance(audit["metadata"], dict)
        assert "tables_cleared" in audit["metadata"]
    finally:
        await _cleanup(conn, user_ids=[user_id], employer_ids=[employer_id])


async def test_hard_delete_audit_columns_match_real_schema(conn):
    """Directly assert the audit_logs INSERT column set the deletion path uses is
    the real schema (actor_id, actor_role, action, entity_type, entity_id,
    metadata, ip_address). A rename on any of these would break the delete flow."""
    cols = {
        r["column_name"]
        for r in await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'audit_logs'"
        )
    }
    for required in (
        "actor_id", "actor_role", "action", "entity_type",
        "entity_id", "metadata", "ip_address",
    ):
        assert required in cols, f"audit_logs is missing column {required!r}"


# ===========================================================================
# 2. Application submit idempotency  (unique constraint + ON CONFLICT)
# ===========================================================================

async def test_application_insert_is_idempotent(conn):
    """The apply path inserts with ON CONFLICT (applicant_id, job_id) DO NOTHING.
    A duplicate submit must not create a second row and must not raise — the
    second insert returns no row (graceful) thanks to the unique constraint."""
    user_id = await _make_user(conn, "applicant")
    applicant_id = await _make_applicant(conn, user_id)
    employer_id = await _make_employer(conn)
    job_id = await _make_job(conn, employer_id, "Itest Apply Target")

    insert_sql = """
        INSERT INTO public.applications
          (applicant_id, job_id, employer_id, status, resume_snapshot, screening_answers)
        VALUES ($1, $2, $3, 'submitted', $4, $5)
        ON CONFLICT (applicant_id, job_id) DO NOTHING
        RETURNING id
    """
    try:
        first = await conn.fetchval(insert_sql, applicant_id, job_id, employer_id, {}, [])
        assert first is not None, "first application insert should succeed"

        # Duplicate (same applicant_id, job_id) — ON CONFLICT DO NOTHING → no row.
        second = await conn.fetchval(insert_sql, applicant_id, job_id, employer_id, {}, [])
        assert second is None, "duplicate insert must be a no-op, not a new row"

        # Exactly one row survives.
        count = await conn.fetchval(
            "SELECT count(*) FROM public.applications WHERE applicant_id = $1 AND job_id = $2",
            applicant_id, job_id,
        )
        assert count == 1

        # The unique constraint the ON CONFLICT relies on really exists.
        has_unique = await conn.fetchval(
            """
            SELECT count(*) FROM pg_constraint
             WHERE conrelid = 'public.applications'::regclass
               AND contype = 'u'
               AND conkey = (
                   SELECT array_agg(attnum ORDER BY attnum)
                     FROM pg_attribute
                    WHERE attrelid = 'public.applications'::regclass
                      AND attname IN ('applicant_id', 'job_id')
               )
            """
        )
        assert has_unique == 1, "expected UNIQUE(applicant_id, job_id) on applications"
    finally:
        await _cleanup(conn, user_ids=[user_id], employer_ids=[employer_id])


# ===========================================================================
# 3. Hire reporting idempotency  (ON CONFLICT DO UPDATE)
# ===========================================================================

async def test_hire_outcome_upsert_is_idempotent(conn):
    """report_hire_outcome upserts on (applicant_id, job_id) DO UPDATE. Reporting
    twice must yield ONE row, with the second report's values winning."""
    user_id = await _make_user(conn, "applicant")
    applicant_id = await _make_applicant(conn, user_id)
    reporter_id = await _make_user(conn, "employer")   # reported_by FK → auth.users
    employer_id = await _make_employer(conn)
    job_id = await _make_job(conn, employer_id, "Itest Hire Target")

    upsert_sql = """
        INSERT INTO public.hire_outcomes
          (applicant_id, job_id, employer_id, outcome_type, notes, reported_by)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6)
        ON CONFLICT (applicant_id, job_id) DO UPDATE
          SET outcome_type = EXCLUDED.outcome_type,
              notes        = EXCLUDED.notes,
              reported_by  = EXCLUDED.reported_by,
              updated_at   = NOW()
        RETURNING id, outcome_type, notes
    """
    try:
        first = await conn.fetchrow(
            upsert_sql, applicant_id, job_id, employer_id, "hired", "first report", reporter_id
        )
        assert first["outcome_type"] == "hired"

        second = await conn.fetchrow(
            upsert_sql, applicant_id, job_id, employer_id, "declined", "changed my mind", reporter_id
        )
        # Same row id (upsert, not insert) with updated values.
        assert second["id"] == first["id"]
        assert second["outcome_type"] == "declined"
        assert second["notes"] == "changed my mind"

        count = await conn.fetchval(
            "SELECT count(*) FROM public.hire_outcomes WHERE applicant_id = $1 AND job_id = $2",
            applicant_id, job_id,
        )
        assert count == 1, "hire report must upsert, never duplicate"
    finally:
        await _cleanup(
            conn, user_ids=[user_id, reporter_id], employer_ids=[employer_id]
        )


# ===========================================================================
# 4. jobs/browse — real rows + pagination
# ===========================================================================

async def test_browse_jobs_returns_rows_and_paginates(conn):
    """Exercise the real browse_jobs router handler against Postgres: it must
    return active jobs and paginate correctly. Self-seeds three uniquely-titled
    active jobs so the test is deterministic in any DB (seeded or freshly
    migrated). The Redis cache layer is bypassed for determinism."""
    import app.routers.jobs as jobs_mod
    from app.auth.schemas import CurrentUser

    employer_id = await _make_employer(conn)
    marker = f"ZZITEST-{uuid.uuid4().hex[:10]}"
    job_ids = [
        await _make_job(conn, employer_id, f"{marker} Electrician {i}")
        for i in range(3)
    ]
    # An inactive job with the same marker must NOT appear (is_active gate).
    await _make_job(conn, employer_id, f"{marker} Inactive", active=False)

    user = CurrentUser(user_id=str(uuid.uuid4()), email="x@test.local", role="applicant")

    @asynccontextmanager
    async def _fake_get_db():
        yield conn

    async def _passthrough_cache(key, ttl, producer):
        # Skip Redis entirely; run the producer directly.
        return await producer()

    try:
        with (
            patch.object(jobs_mod, "get_db", _fake_get_db),
            patch.object(jobs_mod, "cached_json", _passthrough_cache),
        ):
            # Full result set for our marker → exactly the 3 active jobs.
            full = await jobs_mod.browse_jobs(
                user=user, q=marker, trade="", state="", employer="",
                work_setting="", source="",
                near_lat=None, near_lng=None, radius_miles=None, page=1, per_page=20,
            )
            assert full.total == 3, f"expected 3 active jobs, got {full.total}"
            assert len(full.jobs) == 3
            assert all(marker in j.title for j in full.jobs)
            assert full.total_pages == 1

            # Pagination: per_page=2 → page 1 has 2, page 2 has 1, total unchanged.
            p1 = await jobs_mod.browse_jobs(
                user=user, q=marker, trade="", state="", employer="",
                work_setting="", source="",
                near_lat=None, near_lng=None, radius_miles=None, page=1, per_page=2,
            )
            p2 = await jobs_mod.browse_jobs(
                user=user, q=marker, trade="", state="", employer="",
                work_setting="", source="",
                near_lat=None, near_lng=None, radius_miles=None, page=2, per_page=2,
            )
            assert p1.total == 3 and p2.total == 3
            assert p1.total_pages == 2
            assert len(p1.jobs) == 2
            assert len(p2.jobs) == 1
            # No overlap between pages.
            ids_p1 = {j.job_id for j in p1.jobs}
            ids_p2 = {j.job_id for j in p2.jobs}
            assert ids_p1.isdisjoint(ids_p2)
            assert ids_p1 | ids_p2 == set(job_ids)
    finally:
        await _cleanup(conn, employer_ids=[employer_id])
