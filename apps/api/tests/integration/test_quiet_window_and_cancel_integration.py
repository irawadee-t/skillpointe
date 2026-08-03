"""
Live-DB invariants for the rejection quiet window and the interview cancel
path.

Quiet window: rejecting writes the applicant notification with deliver_after
in the future — invisible to the tray query — and a revert inside the window
deletes it (an undone rejection never pings anyone). An uninterrupted
rejection becomes visible once the window passes.

Interview cancel: cancelling a booked (accepted) slot flips it to cancelled,
returns the application to its pre-interview stage, notifies the applicant,
and the personal ICS feed emits STATUS:CANCELLED for the slot's stable UID.

Self-skips when no Postgres is reachable (same pattern as the other
integration tests).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

from app.auth.schemas import CurrentUser

pytestmark = pytest.mark.integration

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:54322/postgres"
)

# The tray API's visibility predicate — asserted against directly so these
# tests fail if the filter and the writer ever drift apart.
_VISIBLE = (
    "SELECT count(*) FROM public.notifications "
    "WHERE recipient_user_id = $1::uuid AND kind = 'application_rejected' "
    "AND (deliver_after IS NULL OR deliver_after <= NOW())"
)
_PENDING = (
    "SELECT count(*) FROM public.notifications "
    "WHERE recipient_user_id = $1::uuid AND kind = 'application_rejected' "
    "AND deliver_after > NOW()"
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


async def _mk_world(conn, *, app_status: str = "reviewed"):
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
        "INSERT INTO public.employers (id, name) VALUES ($1, 'Itest Window Co')", ids["eid"]
    )
    await conn.execute(
        "INSERT INTO public.employer_contacts (employer_id, user_id) VALUES ($1, $2)",
        ids["eid"], ids["emp_uid"],
    )
    await conn.execute(
        "INSERT INTO public.applicants (id, user_id, first_name, last_name) "
        "VALUES ($1, $2, 'Quiet', 'Window')",
        ids["aid"], ids["app_uid"],
    )
    await conn.execute(
        "INSERT INTO public.jobs (id, employer_id, title_raw, is_active) "
        "VALUES ($1, $2, 'Itest Millwright', TRUE)",
        ids["jid"], ids["eid"],
    )
    await conn.execute(
        """
        INSERT INTO public.applications
          (id, applicant_id, job_id, employer_id, status, employer_viewed_at, reviewed_at)
        VALUES ($1, $2, $3, $4, $5::application_status_enum, NOW(), NOW())
        """,
        ids["apid"], ids["aid"], ids["jid"], ids["eid"], app_status,
    )
    return ids


async def _teardown(conn, ids):
    await conn.execute("DELETE FROM public.audit_logs WHERE actor_id = $1::uuid", ids["emp_uid"])
    await conn.execute(
        "DELETE FROM public.notifications WHERE recipient_user_id = ANY($1::uuid[])",
        [ids["emp_uid"], ids["app_uid"]],
    )
    await conn.execute(
        "DELETE FROM public.calendar_feed_secrets WHERE user_id = ANY($1::uuid[])",
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


# ---------------------------------------------------------------------------
# Quiet window
# ---------------------------------------------------------------------------

async def test_reject_revert_inside_window_never_pings(conn):
    from app.routers.applications import (
        ApplicationPatchIn,
        patch_employer_application,
        revert_employer_application,
    )

    ids = await _mk_world(conn)
    try:
        user = _employer_user(ids)
        with _patch_db("applications", conn):
            rejected = await patch_employer_application(
                ids["apid"], ApplicationPatchIn(status="rejected"), user=user
            )
        assert rejected.status == "rejected"

        # The row exists but sits behind the window — invisible to the tray.
        assert await conn.fetchval(_PENDING, ids["app_uid"]) == 1
        assert await conn.fetchval(_VISIBLE, ids["app_uid"]) == 0

        with _patch_db("applications", conn):
            reverted = await revert_employer_application(ids["apid"], user=user)
        assert reverted.status == "reviewed"

        # The pending notification is GONE — the applicant never hears of it.
        assert await conn.fetchval(_PENDING, ids["app_uid"]) == 0
        assert await conn.fetchval(_VISIBLE, ids["app_uid"]) == 0
    finally:
        await _teardown(conn, ids)


async def test_reject_uninterrupted_delivers_after_window(conn):
    from app.routers.applications import (
        ApplicationPatchIn,
        patch_employer_application,
    )

    ids = await _mk_world(conn)
    try:
        user = _employer_user(ids)
        with _patch_db("applications", conn):
            await patch_employer_application(
                ids["apid"], ApplicationPatchIn(status="rejected"), user=user
            )
        assert await conn.fetchval(_VISIBLE, ids["app_uid"]) == 0

        # Fast-forward the clock instead of sleeping through the real window.
        await conn.execute(
            "UPDATE public.notifications SET deliver_after = NOW() - INTERVAL '1 second' "
            "WHERE recipient_user_id = $1::uuid AND kind = 'application_rejected'",
            ids["app_uid"],
        )
        assert await conn.fetchval(_VISIBLE, ids["app_uid"]) == 1
    finally:
        await _teardown(conn, ids)


# ---------------------------------------------------------------------------
# Interview cancel — application restore + honest ICS
# ---------------------------------------------------------------------------

async def test_cancel_booked_interview_restores_stage_and_feeds_cancellation(conn):
    from app.routers.calendar_feed import _get_or_create_secret, calendar_feed
    from app.routers.interviews import CancelIn, cancel_slot
    from app.skilled_pro.signing import make_feed_token

    ids = await _mk_world(conn, app_status="interviewing")
    try:
        await conn.execute(
            "UPDATE public.applications SET previous_status = 'shortlisted' WHERE id = $1::uuid",
            ids["apid"],
        )
        slot_id = str(uuid.uuid4())
        start = datetime.now(timezone.utc) + timedelta(days=2)
        await conn.execute(
            """
            INSERT INTO public.interview_slots
              (id, application_id, proposed_by, start_at, end_at, status, accepted_at)
            VALUES ($1, $2, $3, $4, $5, 'accepted', NOW())
            """,
            slot_id, ids["apid"], ids["emp_uid"], start, start + timedelta(minutes=30),
        )

        user = _employer_user(ids)
        with _patch_db("interviews", conn):
            out = await cancel_slot(
                slot_id, body=CancelIn(reason="Interviewer is out."), user=user
            )
        assert out.status == "cancelled"

        # Application back to its pre-interview stage; history consumed.
        row = await conn.fetchrow(
            "SELECT status::text AS status, previous_status FROM public.applications WHERE id = $1::uuid",
            ids["apid"],
        )
        assert row["status"] == "shortlisted"
        assert row["previous_status"] is None

        # The applicant heard about it, honestly, with the reason.
        note = await conn.fetchrow(
            "SELECT title, body FROM public.notifications "
            "WHERE recipient_user_id = $1::uuid AND kind = 'interview_cancelled'",
            ids["app_uid"],
        )
        assert note is not None
        assert "was cancelled" in note["title"]
        assert "Interviewer is out." in note["body"]

        # The applicant's ICS feed carries the tombstone for the same UID.
        with _patch_db("calendar_feed", conn):
            secret, _ = await _get_or_create_secret(conn, ids["app_uid"])
            token = make_feed_token(ids["app_uid"], secret)
            resp = await calendar_feed(token=token)
        ics = resp.body.decode("utf-8")
        assert f"UID:interview-{slot_id}@skillednation" in ics
        assert "STATUS:CANCELLED" in ics
        assert "SEQUENCE:1" in ics
    finally:
        await _teardown(conn, ids)
