"""
Live-DB invariant tests for the analytics endpoints.

Every dashboard number must be derived from real rows by a logically sound
query. These tests run the ACTUAL endpoint handlers against the real local
Postgres and assert the consistency invariants that make the analytics
trustworthy:

  1. Marketplace funnel (admin overview) is subset-monotonic: stage N >= N+1.
  2. Engagement-summary funnels (applicant + employer) are monotonic and
     pct_of_top is bounded at 1.0; the match-to-apply conversion lens can
     never exceed 100%.
  3. The three admin engagement views agree where they claim the same metric
     (interest signals / candidate views totals vs drill-down sums).
  4. Job-map cluster counts equal the jobs table count under the same filters
     (active + city + state + resolvable coordinates).
  5. A zero-activity applicant (e.g. a freshly imported one) appears in
     population totals but contributes NOTHING to any activity metric or any
     post-signup funnel stage.
  6. Employer analytics are scoped to the employer's own jobs — an employer
     with no jobs sees zeros even while platform-wide signals exist, and the
     per-employer sums can never exceed the platform totals.
  7. Applicant match totals are true DB counts, not the length of the
     display-limited list.

Self-skips when no Postgres is reachable (same pattern as
test_flows_integration.py). Written to be robust to concurrent writers
(imports may be running): assertions are either structural or scoped to
throwaway rows created here.
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
    """Patch app.routers.<module>.get_db to yield the live connection."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=live_conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return patch(f"app.routers.{module}.get_db", return_value=ctx)


def _monotonic(counts: list[int]) -> bool:
    return all(counts[i] >= counts[i + 1] for i in range(len(counts) - 1))


# ---------------------------------------------------------------------------
# 1 + 5. Admin overview: funnel monotonic; zero-activity applicant inert
# ---------------------------------------------------------------------------

async def test_overview_funnel_is_subset_monotonic(conn):
    from app.routers.admin import admin_overview

    with _patch_db("admin", conn):
        data = await admin_overview()

    counts = [s["count"] for s in data["funnel"]]
    assert len(counts) == 7
    assert _monotonic(counts), f"funnel widens mid-way: {counts}"
    # The funnel top is the full population.
    assert counts[0] == data["platform"]["applicants"]


async def test_zero_activity_applicant_contributes_nothing(conn):
    """An imported applicant with no events must count in population totals
    but in NO activity metric and NO post-signup funnel stage."""
    uid, aid = str(uuid.uuid4()), str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO auth.users (id, email) VALUES ($1, $2)",
        uid, f"itest_{uid[:8]}@test.local",
    )
    try:
        await conn.execute(
            "INSERT INTO public.user_profiles (user_id, role) VALUES ($1, 'applicant')", uid
        )
        await conn.execute(
            """
            INSERT INTO public.applicants (id, user_id, first_name, last_name)
            VALUES ($1, $2, 'Zero', 'Activity')
            """,
            aid, uid,
        )

        # No engagement events at all for this applicant.
        n_events = await conn.fetchval(
            "SELECT count(*) FROM public.engagement_events WHERE applicant_id = $1::uuid", aid
        )
        assert n_events == 0

        # Its per-applicant engagement drill-down row (same FILTERs as the
        # endpoint) is all zeros.
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(ee.id) FILTER (WHERE ee.event_type = 'interest_set') AS interest,
                COUNT(ee.id) FILTER (WHERE ee.event_type = 'apply_click')  AS applies,
                COUNT(ee.id)                                               AS total
            FROM public.applicants a
            LEFT JOIN public.engagement_events ee ON ee.applicant_id = a.id
            WHERE a.id = $1::uuid
            GROUP BY a.id
            """,
            aid,
        )
        assert (row["interest"], row["applies"], row["total"]) == (0, 0, 0)

        # It reaches NO cumulative funnel stage beyond "Learners": every stage
        # predicate used by /admin/analytics/overview is false for it.
        stage = await conn.fetchrow(
            """
            SELECT
                EXISTS (SELECT 1 FROM public.credentials c
                        WHERE c.applicant_id = $1::uuid) AS credentialed,
                EXISTS (SELECT 1 FROM public.saved_jobs sj
                        WHERE sj.applicant_id = $1::uuid
                          AND sj.interest_level IN ('interested','applied')) AS interested,
                EXISTS (SELECT 1 FROM public.hire_outcomes ho
                        WHERE ho.applicant_id = $1::uuid) AS placed
            """,
            aid,
        )
        assert not stage["credentialed"] and not stage["interested"] and not stage["placed"]
    finally:
        await conn.execute("DELETE FROM auth.users WHERE id = $1", uid)


# ---------------------------------------------------------------------------
# 2. Engagement summary: funnels monotonic, ratios bounded
# ---------------------------------------------------------------------------

async def test_engagement_summary_funnels_monotonic_and_bounded(conn):
    from app.routers.admin import engagement_summary

    with _patch_db("admin", conn):
        summary = await engagement_summary()

    app_counts = [s.count for s in summary.applicant_funnel]
    emp_counts = [s.count for s in summary.employer_funnel]
    assert _monotonic(app_counts), f"applicant funnel widens: {app_counts}"
    assert _monotonic(emp_counts), f"employer funnel widens: {emp_counts}"
    for step in [*summary.applicant_funnel, *summary.employer_funnel]:
        assert 0.0 <= step.pct_of_top <= 1.0

    conv = next(l for l in summary.lenses if l.lens == "conversion")
    pct = float(conv.value.rstrip("%"))
    assert 0.0 <= pct <= 100.0, f"conversion above 100%: {conv.value}"

    for cohort in summary.retention:
        assert 0.0 <= cohort.pct_returning <= 1.0


# ---------------------------------------------------------------------------
# 3. The three admin engagement views agree on shared metrics
# ---------------------------------------------------------------------------

async def test_engagement_views_agree(conn):
    from app.routers.admin import engagement_analytics

    with _patch_db("admin", conn):
        view1 = await engagement_analytics()

    # View 1 totals equal raw event counts.
    interest_events = await conn.fetchval(
        "SELECT count(*) FROM public.engagement_events WHERE event_type = 'interest_set'"
    )
    apply_events = await conn.fetchval(
        "SELECT count(*) FROM public.engagement_events WHERE event_type = 'apply_click'"
    )
    assert view1.total_interest_signals == interest_events
    assert view1.total_apply_clicks == apply_events

    # Applicant drill-down attributes events by applicant_id; summed over all
    # applicants it must equal the events that carry an applicant_id.
    drill_interest = await conn.fetchval(
        """
        SELECT COALESCE(SUM(n), 0) FROM (
            SELECT COUNT(ee.id) FILTER (WHERE ee.event_type = 'interest_set') AS n
            FROM public.applicants a
            LEFT JOIN public.engagement_events ee ON ee.applicant_id = a.id
            GROUP BY a.id
        ) t
        """
    )
    interest_with_applicant = await conn.fetchval(
        """
        SELECT count(*) FROM public.engagement_events ee
        WHERE ee.event_type = 'interest_set'
          AND ee.applicant_id IN (SELECT id FROM public.applicants)
        """
    )
    assert drill_interest == interest_with_applicant
    assert drill_interest <= interest_events  # never more than the platform total

    # Employer drill-down candidate views sum == candidate_viewed events that
    # carry a known employer_id.
    drill_views = await conn.fetchval(
        """
        SELECT COALESCE(SUM(n), 0) FROM (
            SELECT COUNT(ev.id) FILTER (WHERE ev.event_type = 'candidate_viewed') AS n
            FROM public.employers e
            LEFT JOIN public.engagement_events ev ON ev.employer_id = e.id
            GROUP BY e.id
        ) t
        """
    )
    views_with_employer = await conn.fetchval(
        """
        SELECT count(*) FROM public.engagement_events ee
        WHERE ee.event_type = 'candidate_viewed'
          AND ee.employer_id IN (SELECT id FROM public.employers)
        """
    )
    assert drill_views == views_with_employer


# ---------------------------------------------------------------------------
# 4. Map counts equal the jobs table under the same filters
# ---------------------------------------------------------------------------

async def test_job_map_counts_match_jobs_table(conn):
    from app.routers.admin import _geocode, job_map_data

    with _patch_db("admin", conn):
        clusters = await job_map_data()

    rows = await conn.fetch(
        """
        SELECT city, state, COUNT(*) AS ct
        FROM public.jobs
        WHERE is_active = TRUE AND city IS NOT NULL AND state IS NOT NULL
        GROUP BY city, state
        """
    )
    expected_mapped = sum(int(r["ct"]) for r in rows if _geocode(r["city"], r["state"]))
    assert sum(c.count for c in clusters) == expected_mapped
    # Never more jobs on the map than exist in the table.
    total_active = await conn.fetchval(
        "SELECT count(*) FROM public.jobs WHERE is_active = TRUE"
    )
    assert sum(c.count for c in clusters) <= total_active


# ---------------------------------------------------------------------------
# 6. Employer analytics isolation
# ---------------------------------------------------------------------------

async def test_employer_analytics_scoped_to_own_jobs(conn):
    """An employer with no jobs must see zeros even while other employers'
    jobs have interest/apply signals; per-employer sums <= platform totals."""
    from app.routers.employers import get_employer_analytics

    uid, eid = str(uuid.uuid4()), str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO auth.users (id, email) VALUES ($1, $2)",
        uid, f"itest_{uid[:8]}@test.local",
    )
    try:
        await conn.execute(
            "INSERT INTO public.user_profiles (user_id, role) VALUES ($1, 'employer')", uid
        )
        await conn.execute(
            "INSERT INTO public.employers (id, name) VALUES ($1, 'Itest Isolation Co')", eid
        )
        await conn.execute(
            "INSERT INTO public.employer_contacts (employer_id, user_id) VALUES ($1, $2)",
            eid, uid,
        )

        user = CurrentUser(
            user_id=uid, email="itest@test.local", role="employer",
            onboarding_complete=True,
        )
        with _patch_db("employers", conn):
            analytics = await get_employer_analytics(user)

        assert analytics.outreach_sent == 0
        assert analytics.candidates_interested == 0
        assert analytics.candidates_applied == 0
        assert analytics.hired_count == 0
        assert analytics.recent_outreach == []
        # Application-pipeline fields (added so the analytics page derives its
        # tiles from public.applications — the same table as the inbox). The
        # saved_jobs-based definitions above are unchanged; these are an
        # additional, separately-labeled source. Scoping invariant: an
        # employer with no jobs/applications sees zeros.
        assert analytics.applications_total == 0
        assert analytics.applications_new == 0
        assert analytics.applications_in_review == 0
        assert analytics.applications_interviewing == 0
        assert analytics.applications_hired == 0

        # Per-employer sums (same query, run for every employer) never exceed
        # the platform totals.
        sums = await conn.fetchrow(
            """
            SELECT
              (SELECT COALESCE(SUM(n), 0) FROM (
                 SELECT COUNT(DISTINCT sj.applicant_id) AS n
                 FROM public.saved_jobs sj JOIN public.jobs j ON j.id = sj.job_id
                 WHERE sj.interest_level = 'applied'
                 GROUP BY j.employer_id) t) AS per_emp_applied,
              (SELECT COUNT(*) FROM public.saved_jobs
                WHERE interest_level = 'applied') AS platform_applied,
              (SELECT COALESCE(SUM(n), 0) FROM (
                 SELECT COUNT(*) AS n FROM public.employer_outreach
                 WHERE status = 'sent' GROUP BY employer_id) t) AS per_emp_outreach,
              (SELECT COUNT(*) FROM public.employer_outreach
                WHERE status = 'sent') AS platform_outreach
            """
        )
        assert sums["per_emp_applied"] <= sums["platform_applied"]
        assert sums["per_emp_outreach"] <= sums["platform_outreach"]
    finally:
        await conn.execute("DELETE FROM public.employers WHERE id = $1", eid)
        await conn.execute("DELETE FROM auth.users WHERE id = $1", uid)


async def test_employer_application_pipeline_buckets_partition_total(conn):
    """The employer-analytics pipeline tiles are now derived from
    public.applications with the SAME bucket predicates as the employer inbox
    (new=submitted, in review=reviewed|shortlisted,
    interviewing=interviewing|offered, hired=hired). Structural invariant:
    those buckets plus the terminal rejected/withdrawn states exactly
    partition every employer's application total — no application can be
    double-counted or dropped between the inbox and the analytics page."""
    rows = await conn.fetch(
        """
        SELECT employer_id,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE status = 'submitted') AS new_count,
               COUNT(*) FILTER (WHERE status IN ('reviewed','shortlisted')) AS in_review,
               COUNT(*) FILTER (WHERE status IN ('interviewing','offered')) AS interviewing,
               COUNT(*) FILTER (WHERE status = 'hired') AS hired,
               COUNT(*) FILTER (WHERE status IN ('rejected','withdrawn')) AS terminal
        FROM public.applications
        GROUP BY employer_id
        """
    )
    for r in rows:
        assert (
            r["new_count"] + r["in_review"] + r["interviewing"] + r["hired"] + r["terminal"]
            == r["total"]
        ), f"pipeline buckets do not partition total for employer {r['employer_id']}"


# ---------------------------------------------------------------------------
# 7. Applicant match totals are true counts, not len(limited list)
# ---------------------------------------------------------------------------

async def test_match_totals_are_true_counts_not_list_length(conn):
    from app.routers.applicants import _MAX_MATCHES, get_my_matches

    uid, aid = str(uuid.uuid4()), str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO auth.users (id, email) VALUES ($1, $2)",
        uid, f"itest_{uid[:8]}@test.local",
    )
    try:
        await conn.execute(
            "INSERT INTO public.user_profiles (user_id, role) VALUES ($1, 'applicant')", uid
        )
        await conn.execute(
            """
            INSERT INTO public.applicants (id, user_id, first_name, last_name)
            VALUES ($1, $2, 'Many', 'Matches')
            """,
            aid, uid,
        )
        job_ids = [
            r["id"] for r in await conn.fetch(
                "SELECT id FROM public.jobs WHERE employer_id IS NOT NULL LIMIT $1",
                _MAX_MATCHES + 20,
            )
        ]
        if len(job_ids) <= _MAX_MATCHES:
            pytest.skip("not enough jobs seeded to exceed the display limit")
        await conn.executemany(
            """
            INSERT INTO public.matches
                (applicant_id, job_id, eligibility_status, policy_adjusted_score,
                 is_visible_to_applicant)
            VALUES ($1::uuid, $2, 'eligible', 50, TRUE)
            """,
            [(aid, jid) for jid in job_ids],
        )

        user = CurrentUser(
            user_id=uid, email="itest@test.local", role="applicant",
            onboarding_complete=True,
        )
        with _patch_db("applicants", conn):
            resp = await get_my_matches(user)

        true_count = await conn.fetchval(
            """
            SELECT count(*) FROM public.matches
            WHERE applicant_id = $1::uuid
              AND is_visible_to_applicant = TRUE
              AND eligibility_status = 'eligible'
            """,
            aid,
        )
        assert resp.total_eligible == true_count
        assert resp.total_eligible > _MAX_MATCHES
        assert len(resp.eligible_matches) + len(resp.near_fit_matches) <= _MAX_MATCHES
    finally:
        await conn.execute("DELETE FROM auth.users WHERE id = $1", uid)
