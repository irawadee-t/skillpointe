"""
Employer careers-page pipeline tests (app/skilled_pro/career_sources.py +
app/routers/career_sources.py).

Everything runs offline: HTTP is mocked (or uses IP-literal URLs the SSRF
guard rejects without DNS), and the DB is a small in-memory FakeConn that
mimics the handful of queries the sync path issues.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.skilled_pro import career_sources as cs
from app.skilled_pro.career_sources import (
    _location_from_page,
    check_apply_link,
    discover_job_links,
    filter_trades,
    generic_careers_scrape,
    parse_jsonld_jobpostings,
    plan_sync,
    run_pull,
    scrape_career_source,
    sync_jobs_into_batch,
)

# ---------------------------------------------------------------------------
# Fixture HTML
# ---------------------------------------------------------------------------

JSONLD_PAGE = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "JobPosting",
  "title": "Industrial Electrician",
  "description": "<p>Maintain and repair plant electrical systems.</p>",
  "datePosted": "2026-07-01T00:00:00Z",
  "employmentType": ["FULL_TIME"],
  "identifier": {"@type": "PropertyValue", "value": "REQ-100"},
  "hiringOrganization": {"@type": "Organization", "name": "Acme Mfg"},
  "jobLocation": {"@type": "Place", "address": {
      "@type": "PostalAddress", "addressLocality": "Carrollton", "addressRegion": "Georgia"}},
  "baseSalary": {"@type": "MonetaryAmount",
      "value": {"@type": "QuantitativeValue", "minValue": 28, "maxValue": 36, "unitText": "HOUR"}},
  "url": "https://careers.acme.com/jobs/electrician-100"
}
</script>
<script type="application/ld+json">
{"@graph": [
  {"@type": "Organization", "name": "Acme Mfg"},
  {"@type": "JobPosting", "title": "CNC Machinist II",
   "description": "Run CNC mills.",
   "url": "/jobs/machinist-200"}
]}
</script>
</head><body></body></html>
"""

LINKS_PAGE = """
<html><body>
  <a href="/jobs/industrial-electrician-1">Industrial Electrician</a>
  <a href="/jobs/welder-2">Welder I - Night Shift</a>
  <a href="/jobs/marketing-manager-3">Marketing Manager</a>
  <a href="/jobs/welder-2#apply">Welder I - Night Shift</a>
  <a href="/about">About us</a>
  <a href="/careers/faq">FAQ</a>
  <a href="mailto:hr@acme.com">Email HR</a>
  <a href="https://evil.example.net/jobs/x">External thing</a>
  <a href="https://boards.greenhouse.io/acme/jobs/999?gh_jid=999">Pipefitter</a>
  <a href="/jobs/page/10">The Energy of Change Starts With You</a>
  <a href="/jobs?page=2">Next</a>
  <a href="/jobs?page_number=3">3</a>
  <a href="/jobs/search/?startrow=25">More jobs</a>
</body></html>
"""

DETAIL_PAGE = """
<html><head><title>Welder I | Careers</title></head>
<body><main><h1>Welder I - Night Shift</h1>
<p>Weld steel components in our Carrollton facility.</p>
<h2>Requirements</h2><p>1+ year MIG welding experience.</p>
</main></body></html>
"""


class _FakeResp:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


# ---------------------------------------------------------------------------
# JSON-LD JobPosting parsing
# ---------------------------------------------------------------------------

class TestJsonLdParsing:
    def test_parses_jobposting_fields(self):
        jobs = parse_jsonld_jobpostings(
            JSONLD_PAGE, "https://careers.acme.com/", employer_name="Acme Mfg")
        assert len(jobs) == 2
        first = jobs[0]
        assert first.title == "Industrial Electrician"
        assert first.source_url == "https://careers.acme.com/jobs/electrician-100"
        assert first.city == "Carrollton"
        assert first.state == "GA"          # full name normalized to code
        assert "plant electrical systems" in first.description
        assert first.pay_raw == "$28 - $36 per hour"
        assert first.employment_type == "FULL_TIME"
        assert first.req_id == "REQ-100"
        assert first.posted_date == "2026-07-01"

    def test_graph_and_relative_urls(self):
        jobs = parse_jsonld_jobpostings(
            JSONLD_PAGE, "https://careers.acme.com/", employer_name="Acme Mfg")
        machinist = jobs[1]
        assert machinist.title == "CNC Machinist II"
        # Relative url resolves against the page URL — never the careers root.
        assert machinist.source_url == "https://careers.acme.com/jobs/machinist-200"

    def test_no_jsonld_returns_empty(self):
        assert parse_jsonld_jobpostings(
            "<html><body>no data</body></html>", "https://x.com/", employer_name="X") == []

    def test_malformed_jsonld_is_skipped(self):
        html = '<script type="application/ld+json">{not json</script>'
        assert parse_jsonld_jobpostings(html, "https://x.com/", employer_name="X") == []


# ---------------------------------------------------------------------------
# Anchor-heuristic link discovery
# ---------------------------------------------------------------------------

class TestLinkDiscovery:
    def test_finds_job_links_only(self):
        links = discover_job_links(LINKS_PAGE, "https://careers.acme.com/")
        urls = [u for u, _ in links]
        assert "https://careers.acme.com/jobs/industrial-electrician-1" in urls
        assert "https://careers.acme.com/jobs/welder-2" in urls
        # Non-job chrome and mailto excluded.
        assert not any("/about" in u or "faq" in u or u.startswith("mailto") for u in urls)

    def test_dedupes_fragment_variants(self):
        links = discover_job_links(LINKS_PAGE, "https://careers.acme.com/")
        welder = [u for u, _ in links if "welder-2" in u]
        assert welder == ["https://careers.acme.com/jobs/welder-2"]

    def test_allows_known_ats_offsite_links(self):
        links = discover_job_links(LINKS_PAGE, "https://careers.acme.com/")
        urls = [u for u, _ in links]
        assert any("greenhouse.io" in u for u in urls)
        assert not any("evil.example.net" in u for u in urls)

    def test_pagination_links_are_never_jobs(self):
        # Regression: GE Vernova's /jobs/page/10 pagination link was staged as
        # a "job" titled after the page hero. Pagination paths and page/offset
        # query params must be excluded outright.
        links = discover_job_links(LINKS_PAGE, "https://careers.acme.com/")
        urls = [u for u, _ in links]
        assert not any("/page/" in u for u in urls)
        assert not any("page=" in u or "page_number=" in u or "startrow=" in u for u in urls)


class TestLocationFallback:
    def test_city_state_line_near_top(self):
        body = "Southwire Company\nCarrollton, GA, US, 30119\nWeld things."
        assert _location_from_page(body, "https://x.com/job/foo/1/") == ("Carrollton", "GA")

    def test_state_from_url_slug(self):
        assert _location_from_page(
            "no location here", "https://careers.acme.com/job/Villa-Rica-Welder-GA-30180/99/",
        ) == (None, "GA")

    def test_no_signal_returns_none(self):
        assert _location_from_page("plain text", "https://x.com/job/opening/2") == (None, None)


# ---------------------------------------------------------------------------
# Skilled-trades filter (consumes trades.classify)
# ---------------------------------------------------------------------------

class TestTradesFilter:
    def test_filters_non_trades_and_counts(self):
        from scraper.base import ScrapedJob  # type: ignore

        jobs = [
            ScrapedJob(title="Industrial Electrician", employer_name="A",
                       source_url="https://a.com/jobs/1", source_site="careers:a.com"),
            ScrapedJob(title="Senior Software Engineer", employer_name="A",
                       source_url="https://a.com/jobs/2", source_site="careers:a.com"),
            ScrapedJob(title="Welder I", employer_name="A",
                       source_url="https://a.com/jobs/3", source_site="careers:a.com"),
        ]
        kept, rejected = filter_trades(jobs)
        assert [j.title for j in kept] == ["Industrial Electrician", "Welder I"]
        assert rejected == 1
        # Canonical family from the classifier lands on job_category.
        assert kept[0].job_category
        assert kept[1].job_category


# ---------------------------------------------------------------------------
# Sync planning (dedupe / update / stale)
# ---------------------------------------------------------------------------

class TestPlanSync:
    def test_first_pull_everything_is_new(self):
        new, upd, stale = plan_sync({}, ["u1", "u2"])
        assert (new, upd, stale) == (["u1", "u2"], [], [])

    def test_repull_same_set_updates_in_place(self):
        existing = {"u1": "staged", "u2": "published"}
        new, upd, stale = plan_sync(existing, ["u1", "u2"])
        assert new == []
        assert sorted(upd) == ["u1", "u2"]
        assert stale == []

    def test_vanished_rows_go_stale(self):
        existing = {"u1": "staged", "u2": "published", "u3": "staged"}
        new, upd, stale = plan_sync(existing, ["u1"])
        assert new == []
        assert upd == ["u1"]
        assert sorted(stale) == ["u2", "u3"]

    def test_excluded_and_rejected_rows_are_immune(self):
        existing = {"u1": "excluded", "u2": "rejected"}
        new, upd, stale = plan_sync(existing, ["u1"])
        assert new == []
        assert upd == []      # employer/admin said no — never resurrect
        assert stale == []    # …and never churn their status either

    def test_duplicate_fresh_urls_counted_once(self):
        new, upd, stale = plan_sync({}, ["u1", "u1", "u1"])
        assert new == ["u1"]


# ---------------------------------------------------------------------------
# Apply-link validation (SSRF guard invoked before any fetch)
# ---------------------------------------------------------------------------

class TestApplyLinkCheck:
    def test_private_target_is_blocked_without_network(self):
        # IP literal → guard rejects with zero DNS/HTTP. This is the SSRF path.
        assert check_apply_link("http://169.254.169.254/latest/meta-data/") == "blocked"
        assert check_apply_link("http://127.0.0.1:8000/x") == "blocked"
        assert check_apply_link("ftp://example.com/x") == "blocked"

    def test_ok_and_broken_statuses(self):
        with patch.object(cs, "validate_public_url"), \
             patch.object(cs, "_status_with_safe_redirects", return_value=200):
            assert check_apply_link("https://ok.example.com/j/1") == "ok"
        with patch.object(cs, "validate_public_url"), \
             patch.object(cs, "_status_with_safe_redirects", return_value=404):
            assert check_apply_link("https://gone.example.com/j/1") == "broken"

    def test_head_405_falls_back_to_get(self):
        calls = []

        def fake_status(url, *, method, max_redirects=4):
            calls.append(method)
            return 405 if method == "HEAD" else 200

        with patch.object(cs, "validate_public_url"), \
             patch.object(cs, "_status_with_safe_redirects", side_effect=fake_status):
            assert check_apply_link("https://headless.example.com/j/1") == "ok"
        assert calls == ["HEAD", "GET"]


# ---------------------------------------------------------------------------
# Platform routing + generic fallback (mocked HTTP)
# ---------------------------------------------------------------------------

class TestScrapeRouting:
    def test_known_platform_skips_generic(self):
        from scraper.base import ScrapedJob  # type: ignore

        job = ScrapedJob(title="Wind Technician", employer_name="A",
                         source_url="https://a.wd1.myworkdayjobs.com/en-US/x/job/1",
                         source_site="workday:a")
        with patch.object(cs, "universal_scrape", return_value=("workday", [job])), \
             patch.object(cs, "generic_careers_scrape",
                          side_effect=AssertionError("generic must not run")):
            platform, jobs = scrape_career_source(
                "https://a.wd1.myworkdayjobs.com/x", employer_name="A")
        assert platform == "workday"
        assert jobs == [job]

    def test_unknown_platform_falls_back_to_generic(self):
        from scraper.base import ScrapedJob  # type: ignore

        job = ScrapedJob(title="Welder I", employer_name="A",
                         source_url="https://careers.acme.com/jobs/welder-2",
                         source_site="careers:careers.acme.com")
        with patch.object(cs, "universal_scrape", return_value=("unknown", [])), \
             patch.object(cs, "generic_careers_scrape", return_value=[job]):
            platform, jobs = scrape_career_source(
                "https://careers.acme.com/", employer_name="A")
        assert platform == "generic"
        assert jobs == [job]

    def test_blocked_short_circuits(self):
        with patch.object(cs, "universal_scrape", return_value=("blocked", [])):
            platform, jobs = scrape_career_source("http://127.0.0.1/", employer_name="A")
        assert (platform, jobs) == ("blocked", [])

    def test_generic_scrape_fetches_details_and_parses(self):
        pages = {
            "https://careers.acme.com/": _FakeResp(LINKS_PAGE),
            "https://careers.acme.com/jobs/industrial-electrician-1": _FakeResp(JSONLD_PAGE),
            "https://careers.acme.com/jobs/welder-2": _FakeResp(DETAIL_PAGE),
            "https://boards.greenhouse.io/acme/jobs/999?gh_jid=999": _FakeResp(DETAIL_PAGE),
        }
        fetched = []

        def fake_get(url, **kwargs):
            fetched.append(url)
            return pages.get(url, _FakeResp("nope", status_code=404))

        with patch.object(cs, "safe_get_sync", side_effect=fake_get), \
             patch.object(cs, "_DETAIL_FETCH_DELAY", 0):
            jobs = generic_careers_scrape(
                "https://careers.acme.com/", employer_name="Acme Mfg", max_jobs=10)

        # "Marketing Manager" anchor is early-skipped — its detail page is
        # never fetched (trades-aware discovery).
        assert "https://careers.acme.com/jobs/marketing-manager-3" not in fetched
        titles = {j.title for j in jobs}
        assert "Industrial Electrician" in titles          # detail-page JSON-LD
        assert "Welder I - Night Shift" in titles          # h1 + section parse
        welder = next(j for j in jobs if "Welder" in j.title)
        assert welder.source_url == "https://careers.acme.com/jobs/welder-2"
        assert welder.requirements and "MIG welding" in welder.requirements


# ---------------------------------------------------------------------------
# FakeConn — minimal asyncpg stand-in for the sync/run-pull SQL surface
# ---------------------------------------------------------------------------

class FakeConn:
    def __init__(self, rows=None, batch_exists=True):
        # rows: {source_url: {"id","status","published_job_id", ...fields}}
        self.rows: dict[str, dict] = dict(rows or {})
        self.batch_exists = batch_exists
        self.created_batch_id = None
        self.pull_insert_args = None
        self.source_update_args = None
        self.deactivated_jobs: list[str] = []
        self.refreshed_jobs: list[str] = []

    async def fetch(self, sql, *args):
        if "FROM public.job_import_rows" in sql:
            return [
                {"id": r["id"], "source_url": u, "status": r["status"],
                 "published_job_id": r.get("published_job_id")}
                for u, r in self.rows.items()
            ]
        return []

    async def fetchrow(self, sql, *args):
        if "INSERT INTO public.job_import_batches" in sql:
            self.created_batch_id = str(uuid.uuid4())
            return {"id": self.created_batch_id}
        return None

    async def fetchval(self, sql, *args):
        if "SELECT 1 FROM public.job_import_batches" in sql:
            return 1 if self.batch_exists else None
        if "INSERT INTO public.career_source_pulls" in sql:
            self.pull_insert_args = args
            return "pull-id-1"
        return None

    async def execute(self, sql, *args):
        if "INSERT INTO public.job_import_rows" in sql:
            # args: batch_id, *15 row cols, source_url, link_status
            url, link_status = args[16], args[17]
            self.rows[url] = {"id": str(uuid.uuid4()), "status": "staged",
                              "published_job_id": None, "link_status": link_status,
                              "title": args[1]}
            return
        if "UPDATE public.job_import_rows SET" in sql and "title_raw=$2" in sql:
            # args: id, *15 row cols, next_status, link_status
            for r in self.rows.values():
                if r["id"] == args[0]:
                    r["status"] = args[16]
                    if args[17] is not None:
                        r["link_status"] = args[17]
                    r["title"] = args[1]
            return
        if "SET status='stale'" in sql:
            for r in self.rows.values():
                if r["id"] == args[0]:
                    r["status"] = "stale"
            return
        if "UPDATE public.jobs SET" in sql and "is_active=FALSE" in sql:
            self.deactivated_jobs.append(args[0])
            return
        if "UPDATE public.jobs SET" in sql and "title_raw=$2" in sql:
            self.refreshed_jobs.append(args[0])
            return
        if "UPDATE public.employer_career_sources" in sql:
            self.source_update_args = args
            return
        # batch counter updates etc. — ignore

    def by_status(self, status):
        return sorted(u for u, r in self.rows.items() if r["status"] == status)


def _job(title, url):
    from scraper.base import ScrapedJob  # type: ignore
    return ScrapedJob(title=title, employer_name="Acme",
                      source_url=url, source_site="careers:acme.com")


# ---------------------------------------------------------------------------
# Dedupe/upsert on re-pull + broken-link flagging (DB sync layer)
# ---------------------------------------------------------------------------

class TestSyncIntoBatch:
    async def test_first_sync_inserts_all(self):
        conn = FakeConn()
        counts = await sync_jobs_into_batch(
            conn, "batch-1",
            [_job("Welder I", "https://a.com/j/1"), _job("Electrician", "https://a.com/j/2")],
            {"https://a.com/j/1": "ok", "https://a.com/j/2": "ok"},
        )
        assert counts == {"jobs_new": 2, "jobs_updated": 0, "jobs_removed": 0, "links_broken": 0}
        assert conn.by_status("staged") == ["https://a.com/j/1", "https://a.com/j/2"]

    async def test_repull_updates_in_place_and_marks_stale(self):
        conn = FakeConn(rows={
            "https://a.com/j/1": {"id": "r1", "status": "staged", "published_job_id": None},
            "https://a.com/j/2": {"id": "r2", "status": "published", "published_job_id": "job-2"},
        })
        counts = await sync_jobs_into_batch(
            conn, "batch-1",
            [_job("Welder I (updated)", "https://a.com/j/1"), _job("Millwright", "https://a.com/j/3")],
            {},
        )
        assert counts["jobs_new"] == 1          # j/3
        assert counts["jobs_updated"] == 1      # j/1 refreshed in place
        assert counts["jobs_removed"] == 1      # j/2 vanished
        assert conn.rows["https://a.com/j/1"]["title"] == "Welder I (updated)"
        assert conn.rows["https://a.com/j/2"]["status"] == "stale"
        assert conn.deactivated_jobs == ["job-2"]  # live job closed, not deleted

    async def test_immediate_repull_is_zero_new(self):
        conn = FakeConn()
        jobs = [_job("Welder I", "https://a.com/j/1")]
        await sync_jobs_into_batch(conn, "b", jobs, {})
        counts = await sync_jobs_into_batch(conn, "b", jobs, {})
        assert counts == {"jobs_new": 0, "jobs_updated": 1, "jobs_removed": 0, "links_broken": 0}

    async def test_broken_links_flag_rows(self):
        conn = FakeConn()
        counts = await sync_jobs_into_batch(
            conn, "b",
            [_job("Welder I", "https://a.com/j/1"), _job("Electrician", "https://a.com/j/2")],
            {"https://a.com/j/1": "broken", "https://a.com/j/2": "ok"},
        )
        assert counts["links_broken"] == 1
        assert conn.rows["https://a.com/j/1"]["link_status"] == "broken"
        assert conn.rows["https://a.com/j/2"]["link_status"] == "ok"


# ---------------------------------------------------------------------------
# run_pull end-to-end (mocked scrape + link checks, FakeConn DB)
# ---------------------------------------------------------------------------

class TestRunPull:
    SOURCE = {
        "id": "11111111-1111-1111-1111-111111111111",
        "employer_id": "22222222-2222-2222-2222-222222222222",
        "url": "https://careers.acme.com/",
        "batch_id": None,
        "created_by": "33333333-3333-3333-3333-333333333333",
        "employer_name": "Acme Mfg",
    }

    async def test_full_pull_counts_and_history(self):
        conn = FakeConn()
        scraped = [
            _job("Industrial Electrician", "https://careers.acme.com/jobs/1"),
            _job("Marketing Manager", "https://careers.acme.com/jobs/2"),   # non-trade
            _job("Welder I", "https://careers.acme.com/jobs/3"),
            _job("Root Link", "https://careers.acme.com/"),                 # careers root — dropped
        ]
        with patch.object(cs, "scrape_career_source", return_value=("generic", scraped)), \
             patch.object(cs, "check_apply_links",
                          return_value={"https://careers.acme.com/jobs/1": "ok",
                                        "https://careers.acme.com/jobs/3": "broken"}):
            result = await run_pull(conn, dict(self.SOURCE), triggered_by="user-1")

        assert result["status"] == "ok"
        assert result["jobs_found"] == 4
        assert result["jobs_rejected"] == 1     # marketing manager
        assert result["jobs_new"] == 2          # electrician + welder (root dropped)
        assert result["links_broken"] == 1
        assert result["batch_id"] == conn.created_batch_id
        assert conn.pull_insert_args is not None  # history row recorded
        assert conn.source_update_args is not None  # last_pulled_at/status updated

    async def test_blocked_url_records_blocked_pull(self):
        conn = FakeConn()
        with patch.object(cs, "scrape_career_source", return_value=("blocked", [])):
            result = await run_pull(conn, dict(self.SOURCE), triggered_by="user-1")
        assert result["status"] == "blocked"
        assert result["jobs_new"] == 0
        assert conn.pull_insert_args[3] == "blocked"  # status column on history row
        # Stored/returned error is the human sentence, not guard internals.
        assert result["error"] == cs.HUMAN_ERRORS["blocked"]
        assert "outbound-request guard" not in result["error"]

    async def test_scrape_error_is_recorded_not_raised(self):
        conn = FakeConn()
        with patch.object(cs, "scrape_career_source", side_effect=RuntimeError("boom")):
            result = await run_pull(conn, dict(self.SOURCE), triggered_by="user-1")
        assert result["status"] == "error"
        # Raw exception text is logged only — never stored or returned.
        assert "boom" not in (result["error"] or "")
        assert result["error"] == cs.HUMAN_ERRORS["error"]

    async def test_no_jobs_records_human_error(self):
        conn = FakeConn()
        with patch.object(cs, "scrape_career_source", return_value=("unknown", [])):
            result = await run_pull(conn, dict(self.SOURCE), triggered_by="user-1")
        assert result["status"] == "no_jobs"
        assert result["error"] == cs.HUMAN_ERRORS["no_jobs"]


# ---------------------------------------------------------------------------
# Auto-sync holding state: a source that never produced a job must not keep
# auto-syncing; the first pull with ≥1 job flips auto-sync on.
# ---------------------------------------------------------------------------

class TestAutoSyncHold:
    SOURCE = dict(TestRunPull.SOURCE)

    # In the source-update SQL, $10 (args index 9) is the auto_sync override:
    # True = first success enables, False = never-succeeded hold, None = keep.
    @staticmethod
    def _auto_override(conn):
        return conn.source_update_args[9]

    async def test_never_succeeded_failure_holds_auto_sync_off(self):
        conn = FakeConn()
        with patch.object(cs, "scrape_career_source", return_value=("blocked", [])):
            await run_pull(conn, dict(self.SOURCE), triggered_by="user-1")
        assert self._auto_override(conn) is False

    async def test_first_success_enables_auto_sync(self):
        conn = FakeConn()
        scraped = [_job("Welder I", "https://careers.acme.com/jobs/3")]
        with patch.object(cs, "scrape_career_source", return_value=("generic", scraped)), \
             patch.object(cs, "check_apply_links", return_value={}):
            result = await run_pull(conn, dict(self.SOURCE), triggered_by="user-1")
        assert result["status"] == "ok"
        assert self._auto_override(conn) is True

    async def test_previously_succeeded_source_keeps_employer_setting(self):
        source = {**self.SOURCE, "last_status": "ok", "jobs_found": 3}
        conn = FakeConn()
        with patch.object(cs, "scrape_career_source", side_effect=RuntimeError("boom")):
            await run_pull(conn, source, triggered_by="user-1")
        assert self._auto_override(conn) is None


# ---------------------------------------------------------------------------
# Router: SSRF guard on the user-supplied URL
# ---------------------------------------------------------------------------

class TestSaveSourceEndpoint:
    @pytest.fixture(autouse=True)
    def _clear_overrides(self):
        from app.main import app
        yield
        app.dependency_overrides.clear()

    def _client_as_employer(self):
        from app.auth.dependencies import require_employer_or_admin
        from app.auth.schemas import CurrentUser
        from app.main import app

        app.dependency_overrides[require_employer_or_admin] = lambda: CurrentUser(
            user_id="44444444-4444-4444-4444-444444444444",
            email="employer@test.com", role="employer", onboarding_complete=True,
        )
        return TestClient(app, raise_server_exceptions=False)

    def test_internal_url_rejected_before_any_fetch_or_write(self):
        client = self._client_as_employer()
        db = MagicMock()  # must never be entered
        with patch("app.routers.career_sources.get_db", return_value=db):
            resp = client.post("/employer/me/career-source",
                               json={"url": "http://169.254.169.254/latest/meta-data/"})
        assert resp.status_code == 400
        # Human copy, no guard internals leaked.
        assert "can't reach that address" in resp.json()["detail"]
        db.__aenter__.assert_not_called()

    def test_scheme_restricted(self):
        client = self._client_as_employer()
        resp = client.post("/employer/me/career-source", json={"url": "file:///etc/passwd"})
        assert resp.status_code == 400

    def test_valid_url_saves_with_platform_detected(self):
        client = self._client_as_employer()
        conn = AsyncMock()
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        conn.fetchrow = AsyncMock(side_effect=[
            {"id": "emp-contact"},   # employer resolution
            {"id": "55555555-5555-5555-5555-555555555555",
             "employer_id": "22222222-2222-2222-2222-222222222222",
             "url": "https://acme.wd5.myworkdayjobs.com/External",
             "platform": "workday", "batch_id": None, "last_pulled_at": None,
             "last_status": None, "last_error": None, "jobs_found": 0,
             "created_at": now},
        ])
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=conn)
        ctx.__aexit__ = AsyncMock(return_value=None)
        with patch("app.routers.career_sources.get_db", return_value=ctx), \
             patch("app.routers.career_sources.validate_public_url"):
            resp = client.post("/employer/me/career-source",
                               json={"url": "https://acme.wd5.myworkdayjobs.com/External"})
        assert resp.status_code == 201, resp.text
        assert resp.json()["platform"] == "workday"
