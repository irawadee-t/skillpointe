"""
Live-DB invariants for the application-decision revert flow.

The analytics-truth invariant: marking an application hired and then
reverting it must leave EVERY hire metric exactly where it started —
hire_outcomes count, hire_reported engagement events, the employer
analytics hired_count/applications_hired tiles, and the pipeline-partition
invariant from test_analytics_invariants.py. An undone hire is not a hire.

Also proves the full round-trip against real Postgres: previous_status is
persisted by PATCH, consumed by revert, the audit row lands, and a second
revert is refused.

Self-skips when no Postgres is reachable (same pattern as the other
integration tests).
"""
from __future__ import annotations

import json
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

from app.auth.schemas import CurrentUser

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
    c = await _try_connect()
    if c is None:
        pytest.skip(f"No Postgres reachable at {DATABASE_URL}")
    await c.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    try:
        yield c
    finally:
        await c.close()


def _patch_db(module: str, live_conn: asyncpg.Connection):
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=live_conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch(f"app.routers.{module}.get_db", return_value=ctx)


async def _mk_world(conn):
    """Employer + contact user + applicant (+user) + job + submitted application."""
    ids = {
        "emp_uid": str(uuid.uuid4()), "app_uid": str(uuid.uuid4()),
        "eid": str(uuid.uuid4()), "aid": str(uuid.uuid4()),
        "jid": str(uuid.uuid4()), "apid": str(uuid.uuid4()),
    }
    for uid, role in ((ids["emp_uid"], "employer"), (ids["app_uid"], "applicant")):
        await conn.execute(
            "INSERT INTO auth.users (id, email) VALUES ($1, $2)",
            uid, f"itest_{uid[:8]}@test.local",
        )
        await conn.execute(
            "INSERT INTO public.user_profiles (user_id, role) VALUES ($1, $2)", uid, role
        )
    await conn.execute(
        "INSERT INTO public.employers (id, name) VALUES ($1, 'Itest Revert Co')", ids["eid"]
    )
    await conn.execute(
        "INSERT INTO public.employer_contacts (employer_id, user_id) VALUES ($1, $2)",
        ids["eid"], ids["emp_uid"],
    )
    await conn.execute(
        """
        INSERT INTO public.applicants (id, user_id, first_name, last_name)
        VALUES ($1, $2, 'Revert', 'Case')
        """,
        ids["aid"], ids["app_uid"],
    )
    await conn.execute(
        """
        INSERT INTO public.jobs (id, employer_id, title_raw, is_active)
        VALUES ($1, $2, 'Itest Welder', TRUE)
        """,
        ids["jid"], ids["eid"],
    )
    # employer_viewed_at pre-set so the handlers skip the first-view notify path.
    await conn.execute(
        """
        INSERT INTO public.applications
          (id, applicant_id, job_id, employer_id, status, employer_viewed_at, reviewed_at)
        VALUES ($1, $2, $3, $4, 'reviewed', NOW(), NOW())
        """,
        ids["apid"], ids["aid"], ids["jid"], ids["eid"],
    )
    return ids


async def _teardown(conn, ids):
    # audit_logs.actor_id has no ON DELETE clause — clear our rows first.
    await conn.execute("DELETE FROM public.audit_logs WHERE actor_id = $1::uuid", ids["emp_uid"])
    # Status-change notifications (e.g. "You're hired") reference our users
    # and notifications.recipient_user_id has no ON DELETE clause either.
    await conn.execute(
        "DELETE FROM public.notifications WHERE recipient_user_id = ANY($1::uuid[])",
        [ids["emp_uid"], ids["app_uid"]],
    )
    await conn.execute("DELETE FROM public.employers WHERE id = $1", ids["eid"])
    await conn.execute("DELETE FROM auth.users WHERE id = $1", ids["emp_uid"])
    await conn.execute("DELETE FROM auth.users WHERE id = $1", ids["app_uid"])


def _employer_user(ids) -> CurrentUser:
    return CurrentUser(
        user_id=ids["emp_uid"], email="itest@test.local",
        role="employer", onboarding_complete=True,
    )


async def _hire_metrics(conn, ids) -> dict:
    return {
        "outcomes": await conn.fetchval(
            "SELECT count(*) FROM public.hire_outcomes WHERE applicant_id = $1::uuid AND job_id = $2::uuid",
            ids["aid"], ids["jid"],
        ),
        "events": await conn.fetchval(
            "SELECT count(*) FROM public.engagement_events "
            "WHERE event_type = 'hire_reported' AND applicant_id = $1::uuid AND job_id = $2::uuid",
            ids["aid"], ids["jid"],
        ),
        "apps_hired": await conn.fetchval(
            "SELECT count(*) FROM public.applications WHERE employer_id = $1 AND status = 'hired'",
            ids["eid"],
        ),
    }


async def test_hire_then_revert_leaves_analytics_at_baseline(conn):
    from app.routers.applications import (
        ApplicationPatchIn,
        patch_employer_application,
        revert_employer_application,
    )
    from app.routers.employers import get_employer_analytics

    ids = await _mk_world(conn)
    try:
        user = _employer_user(ids)
        baseline = await _hire_metrics(conn, ids)
        assert baseline == {"outcomes": 0, "events": 0, "apps_hired": 0}

        with _patch_db("applications", conn):
            hired = await patch_employer_application(
                ids["apid"], ApplicationPatchIn(status="hired"), user=user
            )
        assert hired.status == "hired"

        after_hire = await _hire_metrics(conn, ids)
        assert after_hire == {"outcomes": 1, "events": 1, "apps_hired": 1}
        with _patch_db("employers", conn):
            analytics = await get_employer_analytics(user)
        assert analytics.hired_count == 1
        assert analytics.applications_hired == 1

        with _patch_db("applications", conn):
            reverted = await revert_employer_application(ids["apid"], user=user)
        assert reverted.status == "reviewed"

        # THE invariant: every hire metric is back at baseline.
        assert await _hire_metrics(conn, ids) == baseline
        with _patch_db("employers", conn):
            analytics = await get_employer_analytics(user)
        assert analytics.hired_count == 0
        assert analytics.applications_hired == 0

        # Audit row exists with truthful from/to.
        audit = await conn.fetchrow(
            """
            SELECT before_state, after_state FROM public.audit_logs
            WHERE action = 'application_status_reverted' AND entity_id = $1::uuid
            ORDER BY created_at DESC LIMIT 1
            """,
            ids["apid"],
        )
        assert audit is not None
        assert audit["before_state"]["status"] == "hired"
        assert audit["after_state"]["status"] == "reviewed"
        assert audit["before_state"]["hire_outcome"]["outcome_type"] == "hired"
    finally:
        await _teardown(conn, ids)


async def test_full_revert_round_trip_and_double_revert_guard(conn):
    from fastapi import HTTPException

    from app.routers.applications import (
        ApplicationPatchIn,
        patch_employer_application,
        revert_employer_application,
    )

    ids = await _mk_world(conn)
    try:
        user = _employer_user(ids)
        with _patch_db("applications", conn):
            short = await patch_employer_application(
                ids["apid"], ApplicationPatchIn(status="shortlisted"), user=user
            )
        assert short.status == "shortlisted"
        assert await conn.fetchval(
            "SELECT previous_status::text FROM public.applications WHERE id = $1::uuid",
            ids["apid"],
        ) == "reviewed"

        with _patch_db("applications", conn):
            rejected = await patch_employer_application(
                ids["apid"],
                ApplicationPatchIn(status="rejected", decision_note="Itest: not now."),
                user=user,
            )
        assert rejected.status == "rejected"

        # Revert the reject: reopened at the pre-reject stage, note cleared.
        with _patch_db("applications", conn):
            reverted = await revert_employer_application(ids["apid"], user=user)
        assert reverted.status == "shortlisted"
        row = await conn.fetchrow(
            "SELECT decision_note, decision_at, previous_status FROM public.applications WHERE id = $1::uuid",
            ids["apid"],
        )
        assert row["decision_note"] is None
        assert row["decision_at"] is None
        assert row["previous_status"] is None

        # Second revert of the shortlist works (falls back to reviewed since
        # history was consumed)…
        with _patch_db("applications", conn):
            again = await revert_employer_application(ids["apid"], user=user)
        assert again.status == "reviewed"

        # …and a third has nothing left to revert.
        with _patch_db("applications", conn):
            with pytest.raises(HTTPException) as exc:
                await revert_employer_application(ids["apid"], user=user)
        assert exc.value.status_code == 409
    finally:
        await _teardown(conn, ids)
