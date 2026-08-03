"""
Learned-profile incremental sync tests (app/skilled_pro/career_profile.py +
the run_pull routing in career_sources.py + the scheduler tick).

Everything runs offline: HTTP is patched at the single guarded-GET choke
point so tests can assert EXACTLY how many fetches an incremental sync
costs, and the DB is an in-memory fake covering the sync SQL surface.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from app.skilled_pro import career_profile as cp
from app.skilled_pro import career_sources as cs
from app.skilled_pro.career_profile import (
    IncrementalResult,
    ProfileStaleError,
    build_extraction_profile,
    learn_url_patterns,
    scraped_job_fingerprint,
    text_fingerprint,
    url_matches_patterns,
)
from app.skilled_pro.career_sources import run_pull, sync_rows

BASE = "https://careers.acme.com"


def _job(title, url, **kw):
    from scraper.base import ScrapedJob  # type: ignore
    return ScrapedJob(title=title, employer_name="Acme Mfg", source_url=url,
                      source_site="careers:careers.acme.com", **kw)


class FakeResp:
    def __init__(self, text="", status_code=200, headers=None):
        self.text = text
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.is_redirect = False
        self.next_request = None


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestPatternLearning:
    def test_learns_pattern_from_job_urls(self):
        pats = learn_url_patterns([
            f"{BASE}/jobs/electrician-1", f"{BASE}/jobs/welder-2", f"{BASE}/jobs/welder-3",
        ])
        assert len(pats) == 1
        assert url_matches_patterns(f"{BASE}/jobs/brand-new-role-99", pats)
        assert not url_matches_patterns(f"{BASE}/about", pats)
        assert not url_matches_patterns("https://evil.example.net/jobs/x", pats)

    def test_multiple_groups_ordered_by_frequency(self):
        pats = learn_url_patterns([
            f"{BASE}/openings/a", f"{BASE}/openings/b",
            "https://boards.greenhouse.io/acme/jobs/1",
        ])
        assert len(pats) == 2
        assert "openings" in pats[0]

    def test_query_only_variants_still_match(self):
        pats = learn_url_patterns([f"{BASE}/jobs/role-1"])
        assert url_matches_patterns(f"{BASE}/jobs/role-2?src=li#top", pats)


class TestFingerprints:
    def test_content_hash_is_stable_and_sensitive(self):
        a = _job("Welder I", f"{BASE}/jobs/1", description="Weld things")
        b = _job("Welder I", f"{BASE}/jobs/1", description="Weld things")
        c = _job("Welder I", f"{BASE}/jobs/1", description="Weld MORE things")
        assert scraped_job_fingerprint(a) == scraped_job_fingerprint(b)
        assert scraped_job_fingerprint(a) != scraped_job_fingerprint(c)

    def test_listing_fingerprint_normalizes_whitespace_and_case(self):
        assert text_fingerprint("Welder  I ") == text_fingerprint("welder i")
        assert text_fingerprint("Welder I") != text_fingerprint("Welder II")


class TestBuildProfile:
    def test_generic_profile_learns_patterns_and_http(self):
        p = build_extraction_profile(
            platform="generic", url=f"{BASE}/careers",
            job_urls=[f"{BASE}/jobs/a", f"{BASE}/jobs/b"],
            jsonld_listing=False, sitemap_available=True,
            http_meta={"etag": 'W/"x"', "last_modified": None, "supports_304": None},
        )
        assert p["platform"] == "generic"
        assert p["link_patterns"] and url_matches_patterns(f"{BASE}/jobs/c", p["link_patterns"])
        assert p["http"]["etag"] == 'W/"x"'
        assert p["sitemap_available"] is True

    def test_workday_profile_captures_api_params(self):
        p = build_extraction_profile(
            platform="workday", url="https://acme.wd5.myworkdayjobs.com/en-US/External",
            job_urls=[],
        )
        assert p["platform_params"] == {"tenant": "acme", "wd": "wd5", "site": "External"}
        assert p["link_patterns"] == []   # platform APIs don't need anchor patterns


# ---------------------------------------------------------------------------
# In-memory DB fake for the sync + fingerprint + pull-recording SQL surface
# ---------------------------------------------------------------------------

class SyncConn:
    def __init__(self, import_rows=None, career_jobs=None):
        # import_rows: {source_url: {"id","status","published_job_id","title"}}
        self.import_rows: dict[str, dict] = dict(import_rows or {})
        # career_jobs: {source_url: {fingerprint, listing_fingerprint, title, vanished_at}}
        self.career_jobs: dict[str, dict] = dict(career_jobs or {})
        self.pull_inserts: list[tuple] = []
        self.source_updates: list[tuple] = []
        self.review_items: list[dict] = []
        self.created_batch_id = None

    async def fetch(self, sql, *args):
        if "FROM public.career_source_jobs" in sql:
            return [
                {"source_url": u, "title": r.get("title"),
                 "fingerprint": r.get("fingerprint"),
                 "listing_fingerprint": r.get("listing_fingerprint"),
                 "vanished_at": r.get("vanished_at"),
                 "consecutive_misses": r.get("consecutive_misses", 0)}
                for u, r in self.career_jobs.items()
            ]
        if "FROM public.job_import_rows" in sql:
            return [
                {"id": r["id"], "source_url": u, "status": r["status"],
                 "published_job_id": r.get("published_job_id"),
                 "title_raw": r.get("title")}
                for u, r in self.import_rows.items()
            ]
        return []

    async def fetchrow(self, sql, *args):
        if "INSERT INTO public.job_import_batches" in sql:
            self.created_batch_id = str(uuid.uuid4())
            return {"id": self.created_batch_id}
        return None

    async def fetchval(self, sql, *args):
        if "SELECT 1 FROM public.job_import_batches" in sql:
            return 1
        if "INSERT INTO public.career_source_pulls" in sql:
            self.pull_inserts.append(args)
            return f"pull-{len(self.pull_inserts)}"
        return None

    async def execute(self, sql, *args):
        if "INSERT INTO public.career_source_jobs" in sql:
            _sid, url, title, fp, lfp, changed = args
            row = self.career_jobs.setdefault(url, {
                "title": None, "fingerprint": None,
                "listing_fingerprint": None, "vanished_at": None,
            })
            row["title"] = title or row["title"]
            row["fingerprint"] = fp or row["fingerprint"]
            row["listing_fingerprint"] = lfp or row["listing_fingerprint"]
            row["vanished_at"] = None
            row["consecutive_misses"] = 0
            row["changed"] = changed
            return
        if "UPDATE public.career_source_jobs SET" in sql and "consecutive_misses" in sql:
            # Miss accrual + threshold vanish (flap protection).
            keep, threshold = set(args[1]), args[2]
            for url, r in self.career_jobs.items():
                if url not in keep and r.get("vanished_at") is None:
                    r["consecutive_misses"] = r.get("consecutive_misses", 0) + 1
                    if r["consecutive_misses"] >= threshold:
                        r["vanished_at"] = "gone"
            return
        if "INSERT INTO public.job_import_rows" in sql:
            url, link_status = args[16], args[17]
            self.import_rows[url] = {"id": str(uuid.uuid4()), "status": "staged",
                                     "published_job_id": None,
                                     "link_status": link_status, "title": args[1]}
            return
        if "UPDATE public.job_import_rows SET" in sql and "title_raw=$2" in sql:
            for r in self.import_rows.values():
                if r["id"] == args[0]:
                    r["status"] = args[16]
                    r["title"] = args[1]
            return
        if "SET status='stale'" in sql:
            for r in self.import_rows.values():
                if r["id"] == args[0]:
                    r["status"] = "stale"
            return
        if ("UPDATE public.job_import_rows SET status=$2" in sql):
            for r in self.import_rows.values():
                if r["id"] == args[0]:
                    r["status"] = args[1]
            return
        if "UPDATE public.employer_career_sources" in sql:
            self.source_updates.append(args)
            return
        if "INSERT INTO public.review_queue_items" in sql:
            # Guarded by NOT EXISTS on a pending item for this source.
            sid = args[0]
            if not any(i["entity_id"] == sid and i["status"] == "pending"
                       for i in self.review_items):
                self.review_items.append({
                    "item_type": "suspicious_import", "entity_type": "career_source",
                    "entity_id": sid, "description": args[1], "flags": args[2],
                    "status": "pending",
                })
            return
        if "UPDATE public.review_queue_items" in sql:
            for i in self.review_items:
                if i["entity_id"] == args[0] and i["status"] == "pending":
                    i["description"], i["flags"] = args[1], args[2]
            return

    def by_status(self, status):
        return sorted(u for u, r in self.import_rows.items() if r["status"] == status)

    @property
    def last_source_update(self):
        return self.source_updates[-1] if self.source_updates else None

    @property
    def last_pull(self):
        """The last career_source_pulls INSERT args (see run_pull's INSERT)."""
        return self.pull_inserts[-1] if self.pull_inserts else None


SOURCE = {
    "id": "11111111-1111-1111-1111-111111111111",
    "employer_id": "22222222-2222-2222-2222-222222222222",
    "url": f"{BASE}/careers",
    "batch_id": None,
    "created_by": "33333333-3333-3333-3333-333333333333",
    "employer_name": "Acme Mfg",
    "auto_sync_interval_hours": 6,
    "consecutive_failures": 0,
}


def _generic_profile(**over):
    p = {
        "profile_version": 1,
        "platform": "generic",
        "platform_params": {},
        "listing_url": f"{BASE}/careers",
        "link_patterns": learn_url_patterns([f"{BASE}/jobs/seed-1", f"{BASE}/jobs/seed-2"]),
        "jsonld_listing": False,
        "http": {},
    }
    p.update(over)
    return p


# ---------------------------------------------------------------------------
# Event-log payload (sync_rows details)
# ---------------------------------------------------------------------------

class TestSyncDetails:
    async def test_details_carry_titles_and_unchanged_count(self):
        conn = SyncConn(import_rows={
            f"{BASE}/jobs/electrician": {"id": "r1", "status": "staged",
                                         "published_job_id": None, "title": "Electrician"},
            f"{BASE}/jobs/cnc": {"id": "r2", "status": "published",
                                 "published_job_id": "job-9", "title": "CNC Machinist"},
        })
        counters, details = await sync_rows(
            conn, "batch-1",
            [_job("Pipefitter", f"{BASE}/jobs/pipefitter")],
            {f"{BASE}/jobs/pipefitter": "ok"},
            present_urls={f"{BASE}/jobs/electrician", f"{BASE}/jobs/pipefitter"},
        )
        assert counters == {"jobs_new": 1, "jobs_updated": 0, "jobs_removed": 1,
                            "links_broken": 0}
        assert details["added"] == [{"title": "Pipefitter", "url": f"{BASE}/jobs/pipefitter"}]
        assert details["removed"] == [{"title": "CNC Machinist", "url": f"{BASE}/jobs/cnc"}]
        assert details["unchanged"] == 1          # electrician untouched, zero writes
        assert "updated" not in details           # empty lists are dropped

    async def test_stale_row_reappearing_unchanged_is_revived(self):
        conn = SyncConn(import_rows={
            f"{BASE}/jobs/welder": {"id": "r1", "status": "stale",
                                    "published_job_id": None, "title": "Welder I"},
        })
        counters, details = await sync_rows(
            conn, "batch-1", [], {}, present_urls={f"{BASE}/jobs/welder"},
        )
        assert conn.import_rows[f"{BASE}/jobs/welder"]["status"] == "staged"
        assert details["restored"][0]["title"] == "Welder I"
        assert counters["jobs_removed"] == 0


# ---------------------------------------------------------------------------
# Profile persistence on the first (full) pull
# ---------------------------------------------------------------------------

class TestProfilePersistence:
    async def test_first_pull_stores_profile_and_fingerprints(self):
        conn = SyncConn()
        scraped = [
            _job("Industrial Electrician", f"{BASE}/jobs/electrician-1"),
            _job("Welder I", f"{BASE}/jobs/welder-2"),
        ]
        with patch.object(cs, "scrape_career_source", return_value=("generic", scraped)), \
             patch.object(cs, "check_apply_links", return_value={}):
            result = await run_pull(conn, dict(SOURCE), triggered_by="user-1")

        assert result["status"] == "ok"
        assert result["sync_mode"] == "full"
        # Profile persisted on the source row — as a dict: the pooled JSONB
        # codec does the encoding, so a pre-dumped string would double-encode.
        profile = conn.last_source_update[6]
        assert isinstance(profile, dict)
        assert profile["platform"] == "generic"
        assert url_matches_patterns(f"{BASE}/jobs/anything-new", profile["link_patterns"])
        # Per-URL fingerprints recorded for every scraped job.
        assert set(conn.career_jobs) == {f"{BASE}/jobs/electrician-1", f"{BASE}/jobs/welder-2"}
        assert all(r["fingerprint"] for r in conn.career_jobs.values())
        # Success schedules the next auto-sync and resets the failure streak.
        assert conn.last_source_update[7] == 0      # consecutive_failures
        assert conn.last_source_update[8] == 6      # next sync in interval hours


# ---------------------------------------------------------------------------
# Incremental sync: skips discovery, fetches only what changed
# ---------------------------------------------------------------------------

LISTING_HTML = """
<html><body>
  <a href="/jobs/electrician-1">Industrial Electrician</a>
  <a href="/jobs/welder-2">Welder I - Night Shift</a>
  <a href="/jobs/pipefitter-3">Pipefitter</a>
</body></html>
"""

WELDER_DETAIL = """
<html><head><title>Welder</title></head><body><main><h1>Welder I - Night Shift</h1>
<p>Weld steel components in our Carrollton facility all shift long.</p>
<h2>Requirements</h2><p>1+ year MIG welding experience.</p></main></body></html>
"""

PIPEFITTER_DETAIL = """
<html><head><title>Pipefitter</title></head><body><main><h1>Pipefitter</h1>
<p>Install and maintain industrial piping systems across the plant.</p>
<h2>Requirements</h2><p>3+ years pipefitting.</p></main></body></html>
"""


def _stored_for_listing():
    """Fingerprint memory as if a previous sync saw electrician + welder."""
    return {
        f"{BASE}/jobs/electrician-1": {
            "title": "Industrial Electrician",
            "fingerprint": "old-fp-1",
            "listing_fingerprint": text_fingerprint("Industrial Electrician"),
            "vanished_at": None,
        },
        f"{BASE}/jobs/welder-2": {
            "title": "Welder I",
            "fingerprint": "old-fp-2",
            "listing_fingerprint": text_fingerprint("Welder I"),   # anchor changed on site
            "vanished_at": None,
        },
    }


def _http_fixture(extra=None):
    pages = {
        f"{BASE}/careers": FakeResp(LISTING_HTML, headers={"etag": 'W/"v2"'}),
        f"{BASE}/jobs/welder-2": FakeResp(WELDER_DETAIL),
        f"{BASE}/jobs/pipefitter-3": FakeResp(PIPEFITTER_DETAIL),
        **(extra or {}),
    }
    fetched: list[str] = []

    def fake_get(url, *, stats=None, extra_headers=None, max_redirects=4):
        fetched.append(url)
        if stats is not None:
            stats["fetches"] = stats.get("fetches", 0) + 1
        return pages.get(url, FakeResp("gone", status_code=404))

    return fetched, fake_get


class TestIncrementalSync:
    async def test_resync_skips_discovery_and_fetches_only_changed(self):
        conn = SyncConn(
            import_rows={
                f"{BASE}/jobs/electrician-1": {"id": "r1", "status": "staged",
                                               "published_job_id": None,
                                               "title": "Industrial Electrician"},
                f"{BASE}/jobs/welder-2": {"id": "r2", "status": "staged",
                                          "published_job_id": None, "title": "Welder I"},
            },
            career_jobs=_stored_for_listing(),
        )
        source = {**SOURCE, "extraction_profile": _generic_profile()}
        fetched, fake_get = _http_fixture()

        with patch.object(cp, "_guarded_get", side_effect=fake_get), \
             patch.object(cs, "check_apply_links", return_value={}), \
             patch.object(cs, "scrape_career_source",
                          side_effect=AssertionError("full discovery must not run")):
            result = await run_pull(conn, source, triggered_by="user-1")

        assert result["status"] == "ok"
        assert result["sync_mode"] == "incremental"
        # EXACT fetch bill: 1 listing + 2 details (welder changed, pipefitter new).
        assert fetched.count(f"{BASE}/careers") == 1
        assert f"{BASE}/jobs/welder-2" in fetched
        assert f"{BASE}/jobs/pipefitter-3" in fetched
        assert f"{BASE}/jobs/electrician-1" not in fetched   # unchanged → zero fetches
        assert result["fetch_count"] == 3
        assert result["jobs_new"] == 1 and result["jobs_updated"] == 1
        assert result["jobs_found"] == 3
        assert result["details"]["added"][0]["title"] == "Pipefitter"
        assert result["details"]["unchanged"] == 1
        # New posting staged; fingerprint memory refreshed.
        assert f"{BASE}/jobs/pipefitter-3" in conn.by_status("staged")
        assert conn.career_jobs[f"{BASE}/jobs/pipefitter-3"]["fingerprint"]

    async def test_removed_posting_survives_one_miss_then_goes_stale(self):
        """Flap protection: ONE missed listing pull never unpublishes a live
        job — two consecutive misses do (and titles land in the log)."""
        stored = _stored_for_listing()
        stored[f"{BASE}/jobs/cnc-9"] = {
            "title": "CNC Machinist", "fingerprint": "old-fp-9",
            "listing_fingerprint": text_fingerprint("CNC Machinist"), "vanished_at": None,
        }
        conn = SyncConn(
            import_rows={
                f"{BASE}/jobs/cnc-9": {"id": "r9", "status": "published",
                                       "published_job_id": "job-9", "title": "CNC Machinist"},
            },
            career_jobs=stored,
        )
        source = {**SOURCE, "extraction_profile": _generic_profile()}
        fetched, fake_get = _http_fixture()

        # Sync 1 — cnc-9 absent from the listing: grace, NOT stale.
        with patch.object(cp, "_guarded_get", side_effect=fake_get), \
             patch.object(cs, "check_apply_links", return_value={}):
            result = await run_pull(conn, source, triggered_by="user-1")
        assert result["jobs_removed"] == 0
        assert "removed" not in result["details"]
        assert conn.import_rows[f"{BASE}/jobs/cnc-9"]["status"] == "published"
        cnc = conn.career_jobs[f"{BASE}/jobs/cnc-9"]
        assert cnc["vanished_at"] is None and cnc["consecutive_misses"] == 1

        # Sync 2 — still absent: second consecutive miss → stale + vanished.
        with patch.object(cp, "_guarded_get", side_effect=fake_get), \
             patch.object(cs, "check_apply_links", return_value={}):
            result = await run_pull(conn, source, triggered_by="user-1")
        assert result["jobs_removed"] == 1
        assert result["details"]["removed"][0]["title"] == "CNC Machinist"
        assert conn.import_rows[f"{BASE}/jobs/cnc-9"]["status"] == "stale"
        assert conn.career_jobs[f"{BASE}/jobs/cnc-9"]["vanished_at"] is not None

    async def test_reappearance_resets_miss_counter(self):
        """A posting that misses once and then reappears resets to zero misses
        — no lingering half-stale state."""
        stored = _stored_for_listing()
        stored[f"{BASE}/jobs/welder-2"]["consecutive_misses"] = 1   # missed last sync
        conn = SyncConn(
            import_rows={
                f"{BASE}/jobs/welder-2": {"id": "r2", "status": "published",
                                          "published_job_id": "job-2", "title": "Welder I"},
            },
            career_jobs=stored,
        )
        source = {**SOURCE, "extraction_profile": _generic_profile()}
        fetched, fake_get = _http_fixture()
        with patch.object(cp, "_guarded_get", side_effect=fake_get), \
             patch.object(cs, "check_apply_links", return_value={}):
            result = await run_pull(conn, source, triggered_by="user-1")
        assert result["status"] == "ok"
        w = conn.career_jobs[f"{BASE}/jobs/welder-2"]
        assert w["consecutive_misses"] == 0 and w["vanished_at"] is None
        assert conn.import_rows[f"{BASE}/jobs/welder-2"]["status"] == "published"

    async def test_304_short_circuits_to_no_changes(self):
        conn = SyncConn(career_jobs=_stored_for_listing())
        source = {**SOURCE, "extraction_profile": _generic_profile(
            http={"etag": 'W/"v1"', "last_modified": None, "supports_304": None})}
        seen_headers = {}

        def fake_get(url, *, stats=None, extra_headers=None, max_redirects=4):
            seen_headers.update(extra_headers or {})
            if stats is not None:
                stats["fetches"] = stats.get("fetches", 0) + 1
            return FakeResp("", status_code=304)

        with patch.object(cp, "_guarded_get", side_effect=fake_get), \
             patch.object(cs, "scrape_career_source",
                          side_effect=AssertionError("must not rescrape")):
            result = await run_pull(conn, source, triggered_by="user-1")

        assert seen_headers.get("If-None-Match") == 'W/"v1"'
        assert result["sync_mode"] == "not_modified"
        assert result["status"] == "ok"
        assert result["fetch_count"] == 1                 # the conditional GET, nothing else
        assert result["jobs_found"] == 2                  # known live jobs, honestly reported
        assert result["details"]["unchanged"] == 2
        # Measured capability persisted: the site honours validators.
        profile = conn.last_source_update[6]
        assert profile["http"]["supports_304"] is True

    async def test_structure_change_falls_back_and_relearns(self):
        conn = SyncConn(career_jobs=_stored_for_listing())
        source = {**SOURCE, "extraction_profile": _generic_profile()}
        # Site redesigned: listing now has no recognizable job links at all.
        fetched, fake_get = _http_fixture(
            extra={f"{BASE}/careers": FakeResp("<html><body>All new SPA</body></html>")})
        relearned_jobs = [_job("Millwright", f"{BASE}/positions/millwright-7")]

        with patch.object(cp, "_guarded_get", side_effect=fake_get), \
             patch.object(cs, "check_apply_links", return_value={}), \
             patch.object(cs, "scrape_career_source",
                          return_value=("generic", relearned_jobs)) as full:
            result = await run_pull(conn, source, triggered_by="user-1")

        assert full.called                                # fell back to discovery
        assert result["sync_mode"] == "relearned"
        assert result["status"] == "ok"
        assert result["details"]["relearned"] is True
        assert "relearned" in result["details"]["note"].lower() or \
               "structure" in result["details"]["note"].lower()
        # Profile rebuilt around the NEW structure.
        profile = conn.last_source_update[6]
        assert url_matches_patterns(f"{BASE}/positions/other-role", profile["link_patterns"])

    async def test_incremental_failure_backs_off(self):
        conn = SyncConn(career_jobs=_stored_for_listing())
        source = {**SOURCE, "extraction_profile": _generic_profile(),
                  "consecutive_failures": 2}

        def fake_get(url, **kw):
            raise cp.httpx.ConnectError("boom")

        with patch.object(cp, "_guarded_get", side_effect=fake_get), \
             patch.object(cs, "scrape_career_source", return_value=("unknown", [])):
            result = await run_pull(conn, source, triggered_by="user-1")

        assert result["status"] == "no_jobs"
        assert conn.last_source_update[7] == 3            # failure streak grows
        assert conn.last_source_update[8] == 6 * 4        # exponential backoff (×2^2)


class TestIncrementalUnitPaths:
    def test_generic_incremental_raises_when_profile_dead(self):
        stored = _stored_for_listing()
        with patch.object(cp, "_guarded_get",
                          return_value=FakeResp("<html>nothing here</html>")):
            try:
                cp._generic_incremental(
                    f"{BASE}/careers", _generic_profile(), stored,
                    employer_name="Acme", max_jobs=50, stats={}, http_meta={})
                raise AssertionError("expected ProfileStaleError")
            except ProfileStaleError:
                pass

    def test_pattern_mismatch_falls_back_to_raw_anchors_once(self):
        # Learned patterns point at /jobs/… but the site moved to /openings/…;
        # raw heuristic anchors still resolve so the sync limps through.
        html = f'<a href="{BASE}/openings/welder-1">Welder I</a>'
        detail = WELDER_DETAIL
        pages = {
            f"{BASE}/careers": FakeResp(html),
            f"{BASE}/openings/welder-1": FakeResp(detail),
        }
        with patch.object(cp, "_guarded_get",
                          side_effect=lambda url, **kw: pages.get(url, FakeResp("", 404))):
            res = cp._generic_incremental(
                f"{BASE}/careers", _generic_profile(), {},
                employer_name="Acme", max_jobs=50, stats={}, http_meta={})
        assert isinstance(res, IncrementalResult)
        assert f"{BASE}/openings/welder-1" in res.present
        assert res.jobs and res.jobs[0].title.startswith("Welder")


# ---------------------------------------------------------------------------
# Adaptive cadence — zero-change streaks relax the interval; changes tighten
# ---------------------------------------------------------------------------

class TestAdaptiveCadence:
    """UPDATE args: [7]=failures [8]=delay_h [10]=no_change_streak
    [11]=adaptive_interval_hours (None = at base)."""

    async def test_no_change_streak_relaxes_interval(self):
        conn = SyncConn(career_jobs=_stored_for_listing())
        source = {**SOURCE, "no_change_streak": 5, "adaptive_interval_hours": None,
                  "extraction_profile": _generic_profile(
                      http={"etag": 'W/"v1"', "last_modified": None, "supports_304": None})}

        def fake_get(url, *, stats=None, extra_headers=None, max_redirects=4):
            if stats is not None:
                stats["fetches"] = stats.get("fetches", 0) + 1
            return FakeResp("", status_code=304)

        with patch.object(cp, "_guarded_get", side_effect=fake_get):
            result = await run_pull(conn, source, triggered_by=None)

        assert result["status"] == "ok"
        upd = conn.last_source_update
        assert upd[8] == 12          # 6h base ×2 after 6 zero-change syncs
        assert upd[10] == 0          # streak resets after each relaxation
        assert upd[11] == 12         # persisted adaptive interval
        assert "relaxed to every 12h" in result["details"]["cadence"]

    async def test_relaxation_caps_at_24h(self):
        conn = SyncConn(career_jobs=_stored_for_listing())
        source = {**SOURCE, "no_change_streak": 5, "adaptive_interval_hours": 24,
                  "extraction_profile": _generic_profile(
                      http={"etag": 'W/"v1"', "last_modified": None, "supports_304": None})}

        def fake_get(url, *, stats=None, extra_headers=None, max_redirects=4):
            if stats is not None:
                stats["fetches"] = stats.get("fetches", 0) + 1
            return FakeResp("", status_code=304)

        with patch.object(cp, "_guarded_get", side_effect=fake_get):
            result = await run_pull(conn, source, triggered_by=None)
        upd = conn.last_source_update
        assert upd[8] == 24 and upd[11] == 24     # already at the cap
        assert "cadence" not in result["details"]  # nothing changed — no log noise

    async def test_observed_change_tightens_back_to_base(self):
        conn = SyncConn(
            import_rows={
                f"{BASE}/jobs/electrician-1": {"id": "r1", "status": "staged",
                                               "published_job_id": None,
                                               "title": "Industrial Electrician"},
            },
            career_jobs=_stored_for_listing(),
        )
        source = {**SOURCE, "no_change_streak": 3, "adaptive_interval_hours": 24,
                  "extraction_profile": _generic_profile()}
        fetched, fake_get = _http_fixture()
        with patch.object(cp, "_guarded_get", side_effect=fake_get), \
             patch.object(cs, "check_apply_links", return_value={}):
            result = await run_pull(conn, source, triggered_by="user-1")

        assert result["jobs_new"] >= 1            # pipefitter appeared
        upd = conn.last_source_update
        assert upd[8] == 6                        # back to the employer base
        assert upd[10] == 0 and upd[11] is None   # adaptation cleared
        assert "tightened back to every 6h" in result["details"]["cadence"]

    async def test_short_streak_keeps_base_interval(self):
        conn = SyncConn(career_jobs=_stored_for_listing())
        source = {**SOURCE, "no_change_streak": 1,
                  "extraction_profile": _generic_profile(
                      http={"etag": 'W/"v1"', "last_modified": None, "supports_304": None})}

        def fake_get(url, *, stats=None, extra_headers=None, max_redirects=4):
            if stats is not None:
                stats["fetches"] = stats.get("fetches", 0) + 1
            return FakeResp("", status_code=304)

        with patch.object(cp, "_guarded_get", side_effect=fake_get):
            result = await run_pull(conn, source, triggered_by=None)
        upd = conn.last_source_update
        assert upd[8] == 6 and upd[10] == 2 and upd[11] is None
        assert "cadence" not in result["details"]


# ---------------------------------------------------------------------------
# Headless fallback — JS-walled listings via the rendered-DOM path
# ---------------------------------------------------------------------------

JSONLD_LISTING = """
<html><body><script type="application/ld+json">
{"@type": "JobPosting", "title": "Industrial Electrician",
 "url": "https://careers.acme.com/jobs/industrial-electrician-1",
 "description": "Repair industrial controls.",
 "jobLocation": {"address": {"addressLocality": "Nashville",
                             "addressRegion": "TN"}}}
</script></body></html>
"""


class TestHeadlessPull:
    async def test_headless_pull_syncs_rendered_listing(self):
        from app.skilled_pro.career_sources import run_headless_pull

        conn = SyncConn()
        source = {**SOURCE}
        with patch("app.skilled_pro.headless.render_listing_html",
                   return_value=JSONLD_LISTING), \
             patch.object(cs, "validate_public_url", lambda u: u), \
             patch.object(cs, "check_apply_links", return_value={}):
            result = await run_headless_pull(conn, source, triggered_by=None)

        assert result["status"] == "ok"
        assert result["sync_mode"] == "headless"
        assert result["jobs_new"] == 1
        url = "https://careers.acme.com/jobs/industrial-electrician-1"
        assert conn.import_rows[url]["status"] == "staged"
        assert conn.career_jobs[url]["fingerprint"]
        # Source marked headless so auto-sync keeps routing here (daily).
        profile = conn.last_source_update[6]
        assert profile["headless"] is True and profile["platform"] == "headless"
        assert conn.last_source_update[9] == 24   # daily cadence, not 6h

    async def test_headless_finding_nothing_stays_honest(self):
        from app.skilled_pro.career_sources import run_headless_pull

        conn = SyncConn()
        with patch("app.skilled_pro.headless.render_listing_html",
                   return_value=None), \
             patch.object(cs, "validate_public_url", lambda u: u):
            result = await run_headless_pull(conn, dict(SOURCE), triggered_by=None)

        assert result["status"] == "no_jobs"
        assert result["error"]                     # human sentence, not silence
        assert conn.import_rows == {}              # nothing fabricated
        profile = conn.last_source_update[6]
        assert profile is None                     # no headless marking

    async def test_headless_respects_disable_flag(self, monkeypatch):
        from app.config import get_settings
        from app.skilled_pro.career_sources import run_headless_pull

        conn = SyncConn()
        settings = get_settings()
        monkeypatch.setattr(settings, "headless_scrape_enabled", False)
        try:
            result = await run_headless_pull(conn, dict(SOURCE), triggered_by=None)
        finally:
            monkeypatch.setattr(settings, "headless_scrape_enabled", True)
        assert result["status"] == "blocked"


# ---------------------------------------------------------------------------
# Scheduler tick — due sources run through the incremental pull
# ---------------------------------------------------------------------------

class TestSchedulerTick:
    async def test_tick_pulls_due_sources(self, monkeypatch):
        from app.worker.scheduler import _career_source_auto_sync_tick

        due = {**SOURCE, "extraction_profile": _generic_profile(),
               "auto_sync_enabled": True}
        pulled = []

        class TickConn:
            async def fetch(self, sql, *args):
                assert "auto_sync_enabled" in sql and "next_auto_sync_at" in sql
                return [due]

        class Ctx:
            async def __aenter__(self):
                return TickConn()
            async def __aexit__(self, *a):
                return None

        async def fake_run_pull(conn, source, *, triggered_by=None, **kw):
            pulled.append((source["id"], triggered_by))
            return {"status": "ok", "sync_mode": "incremental", "duration_ms": 42,
                    "jobs_new": 0, "jobs_updated": 0, "jobs_removed": 0}

        monkeypatch.setattr("app.db.get_db", lambda: Ctx())
        monkeypatch.setattr("app.skilled_pro.career_sources.run_pull", fake_run_pull)

        await _career_source_auto_sync_tick()
        assert pulled == [(SOURCE["id"], None)]   # scheduled runs have no user

    async def test_tick_noop_when_nothing_due(self, monkeypatch):
        class TickConn:
            async def fetch(self, sql, *args):
                return []

        class Ctx:
            async def __aenter__(self):
                return TickConn()
            async def __aexit__(self, *a):
                return None

        called = []

        async def fake_run_pull(*a, **kw):
            called.append(1)
            return {}

        monkeypatch.setattr("app.db.get_db", lambda: Ctx())
        monkeypatch.setattr("app.skilled_pro.career_sources.run_pull", fake_run_pull)
        from app.worker.scheduler import _career_source_auto_sync_tick
        await _career_source_auto_sync_tick()
        assert called == []


# ---------------------------------------------------------------------------
# Listing completeness + removal blast radius
#
# The rule these tests pin down: a posting's ABSENCE only means something when
# the crawl saw the whole listing. A first-page-only crawl once read as "every
# posting below the fold was removed" and deactivated 283 of 400 live jobs in
# two auto-sync ticks.
# ---------------------------------------------------------------------------

PAGE_1 = """
<html><body>
  <a href="/jobs/electrician-1">Industrial Electrician</a>
  <a href="/jobs/welder-2">Welder I - Night Shift</a>
  <a href="/jobs/pipefitter-3">Pipefitter</a>
  <a href="/careers?page=2">Next</a>
</body></html>
"""

PAGE_2 = """
<html><body>
  <a href="/jobs/millwright-4">Millwright</a>
  <a href="/careers?page=1">Previous</a>
</body></html>
"""

MILLWRIGHT_DETAIL = """
<html><head><title>Millwright</title></head><body><main><h1>Millwright</h1>
<p>Install, align and maintain rotating plant equipment on every shift.</p>
<h2>Requirements</h2><p>2+ years millwright experience.</p></main></body></html>
"""


def _paged_fixture(*, page_2=PAGE_2, page_1_alias=PAGE_1):
    """Listing paginated over two pages (page 2 links back to ?page=1)."""
    pages = {
        f"{BASE}/careers": FakeResp(PAGE_1),
        f"{BASE}/careers?page=2": FakeResp(page_2) if page_2 else FakeResp("", 404),
        f"{BASE}/careers?page=1": FakeResp(page_1_alias) if page_1_alias
        else FakeResp("", 404),
        f"{BASE}/jobs/welder-2": FakeResp(WELDER_DETAIL),
        f"{BASE}/jobs/pipefitter-3": FakeResp(PIPEFITTER_DETAIL),
        f"{BASE}/jobs/millwright-4": FakeResp(MILLWRIGHT_DETAIL),
    }
    fetched: list[str] = []

    def fake_get(url, *, stats=None, extra_headers=None, max_redirects=4):
        fetched.append(url)
        if stats is not None:
            stats["fetches"] = stats.get("fetches", 0) + 1
        return pages.get(url, FakeResp("gone", status_code=404))

    return fetched, fake_get


class TestPaginationDiscovery:
    def test_finds_numbered_and_next_page_links(self):
        links = cs.discover_pagination_links(PAGE_1, f"{BASE}/careers")
        assert links == [f"{BASE}/careers?page=2"]

    def test_ignores_other_hosts_and_the_page_itself(self):
        html = (
            f'<a href="{BASE}/careers?page=2">2</a>'
            '<a href="https://elsewhere.example/careers?page=2">2</a>'
            f'<a href="{BASE}/careers">1</a>'
        )
        assert cs.discover_pagination_links(html, f"{BASE}/careers") == [
            f"{BASE}/careers?page=2"]

    def test_job_links_are_never_mistaken_for_pagination(self):
        assert cs.discover_pagination_links(
            f'<a href="{BASE}/jobs/welder-2">Welder</a>', f"{BASE}/careers") == []

    def test_crawl_walks_to_the_end_and_reports_complete(self):
        served = {f"{BASE}/careers?page=2": PAGE_2, f"{BASE}/careers?page=1": PAGE_1}
        pages, complete, reason = cs.crawl_listing_pages(
            f"{BASE}/careers", PAGE_1, served.get)
        assert [u for u, _ in pages] == [
            f"{BASE}/careers", f"{BASE}/careers?page=2", f"{BASE}/careers?page=1"]
        assert complete is True and reason is None

    def test_crawl_reports_incomplete_when_a_page_cannot_be_read(self):
        pages, complete, reason = cs.crawl_listing_pages(
            f"{BASE}/careers", PAGE_1, lambda _u: None)
        assert len(pages) == 1
        assert complete is False and reason == "page_fetch_failed"

    def test_crawl_reports_incomplete_at_the_page_bound(self):
        # Every page offers one more page: the bound must stop the walk and
        # say so rather than looping.
        def endless(url: str) -> str:
            n = int(url.rsplit("=", 1)[1])
            return f'<a href="{BASE}/careers?page={n + 1}">Next</a>'

        pages, complete, reason = cs.crawl_listing_pages(
            f"{BASE}/careers", PAGE_1, endless)
        assert len(pages) == cs.MAX_LISTING_PAGES
        assert complete is False and reason == "page_bound"


class TestFullScrapeCompleteness:
    """The first/relearn pull walks pagination too, and a max_jobs cap makes
    the census incomplete rather than silently short."""

    def _serve(self, pages):
        def fake_get(url, **kw):
            return FakeResp(pages.get(url, ""), 200 if url in pages else 404)
        return fake_get

    def test_full_scrape_paginates_and_reports_complete(self):
        pages = {
            f"{BASE}/careers": PAGE_1,
            f"{BASE}/careers?page=2": PAGE_2,
            f"{BASE}/careers?page=1": PAGE_1,
            f"{BASE}/jobs/electrician-1": WELDER_DETAIL,
            f"{BASE}/jobs/welder-2": WELDER_DETAIL,
            f"{BASE}/jobs/pipefitter-3": PIPEFITTER_DETAIL,
            f"{BASE}/jobs/millwright-4": MILLWRIGHT_DETAIL,
        }
        stats: dict = {}
        with patch.object(cs, "safe_get_sync", side_effect=self._serve(pages)), \
             patch.object(cs.time, "sleep", lambda _s: None):
            jobs = cs.generic_careers_scrape(
                f"{BASE}/careers", employer_name="Acme Mfg", stats=stats)
        assert stats["listing_complete"] is True
        assert stats["listing_pages"] == 3
        assert {j.source_url for j in jobs} >= {f"{BASE}/jobs/millwright-4"}

    def test_max_jobs_cap_marks_the_census_incomplete(self):
        pages = {
            f"{BASE}/careers": PAGE_1,
            f"{BASE}/careers?page=2": PAGE_2,
            f"{BASE}/careers?page=1": PAGE_1,
            f"{BASE}/jobs/welder-2": WELDER_DETAIL,
        }
        stats: dict = {}
        with patch.object(cs, "safe_get_sync", side_effect=self._serve(pages)), \
             patch.object(cs.time, "sleep", lambda _s: None):
            cs.generic_careers_scrape(f"{BASE}/careers", employer_name="Acme Mfg",
                                      max_jobs=2, stats=stats)
        assert stats["listing_complete"] is False
        assert stats["incomplete_reason"] == "max_jobs_cap"

    def test_listing_fetch_failure_is_never_a_complete_census(self):
        stats: dict = {}
        with patch.object(cs, "safe_get_sync",
                          side_effect=cs.httpx.ConnectError("boom")):
            assert cs.generic_careers_scrape(
                f"{BASE}/careers", employer_name="Acme Mfg", stats=stats) == []
        assert stats["listing_complete"] is False


class TestBlastRadius:
    def test_threshold_is_the_larger_of_30_percent_and_25(self):
        assert cs.blast_radius_threshold(10) == 25       # floor wins on small sources
        assert cs.blast_radius_threshold(400) == 120     # 30% wins on big ones

    def test_ordinary_churn_passes(self):
        assert cs.exceeds_blast_radius(3, 120) is False
        assert cs.exceeds_blast_radius(0, 0) is False

    def test_mass_removal_trips(self):
        assert cs.exceeds_blast_radius(74, 83) is True   # the Southwire outage

    def test_plan_removals_protects_everything_on_an_incomplete_crawl(self):
        stored = {"a": {"consecutive_misses": 1}, "b": {"consecutive_misses": 1}}
        mode, protected, would, live = cs.plan_removals(
            stored, {"a"}, listing_complete=False)
        assert mode == "skipped_incomplete"
        assert protected == {"a", "b"} and would == 0 and live == 2

    def test_plan_removals_applies_within_the_radius(self):
        stored = {f"u{i}": {"consecutive_misses": 1} for i in range(30)}
        mode, protected, would, live = cs.plan_removals(
            stored, set(list(stored)[:29]), listing_complete=True)
        assert mode == "applied" and would == 1 and live == 30
        assert protected == set()                        # grace already spent


class TestListingCompleteness:
    async def test_partial_listing_stales_nothing(self):
        """Page two is unreachable, so the postings only listed there were
        never looked for. Absence must not read as removal."""
        stored = _stored_for_listing()
        stored[f"{BASE}/jobs/millwright-4"] = {
            "title": "Millwright", "fingerprint": "old-fp-4",
            "listing_fingerprint": text_fingerprint("Millwright"),
            "vanished_at": None, "consecutive_misses": 1,   # one miss already
        }
        conn = SyncConn(
            import_rows={
                f"{BASE}/jobs/millwright-4": {"id": "r4", "status": "published",
                                              "published_job_id": "job-4",
                                              "title": "Millwright"},
            },
            career_jobs=stored,
        )
        source = {**SOURCE, "extraction_profile": _generic_profile()}
        _fetched, fake_get = _paged_fixture(page_2=None)

        with patch.object(cp, "_guarded_get", side_effect=fake_get), \
             patch.object(cs, "check_apply_links", return_value={}):
            result = await run_pull(conn, source, triggered_by="user-1")

        assert result["status"] == "ok"
        assert result["listing_complete"] is False
        assert result["removal_detection"] == "skipped_incomplete"
        assert result["jobs_removed"] == 0
        # Nothing staled, nothing deactivated, no miss accrued.
        assert conn.import_rows[f"{BASE}/jobs/millwright-4"]["status"] == "published"
        mw = conn.career_jobs[f"{BASE}/jobs/millwright-4"]
        assert mw["consecutive_misses"] == 1 and mw["vanished_at"] is None
        # And the timeline says so in plain words.
        assert "last page" in result["details"]["removal_note"]
        assert conn.last_pull[16] is False                      # listing_complete
        assert conn.last_pull[17] == "skipped_incomplete"       # removal_detection

    async def test_full_pagination_walk_finds_every_page_and_allows_removals(self):
        conn = SyncConn(career_jobs=_stored_for_listing())
        source = {**SOURCE, "extraction_profile": _generic_profile()}
        fetched, fake_get = _paged_fixture()

        with patch.object(cp, "_guarded_get", side_effect=fake_get), \
             patch.object(cs, "check_apply_links", return_value={}):
            result = await run_pull(conn, source, triggered_by="user-1")

        assert f"{BASE}/careers?page=2" in fetched
        assert result["listing_complete"] is True
        assert result["removal_detection"] == "applied"
        assert result["details"]["listing_pages"] == 3     # 1 → ?page=2 → ?page=1
        # The page-two posting is a real find, not a phantom.
        assert result["jobs_found"] == 4
        assert f"{BASE}/jobs/millwright-4" in conn.career_jobs
        assert "Millwright" in [e["title"] for e in result["details"]["added"]]

    async def test_complete_listing_still_stales_a_genuinely_removed_job(self):
        """The guard must not blunt the real feature: two consecutive misses on
        a complete crawl still unpublish a posting."""
        stored = _stored_for_listing()
        stored[f"{BASE}/jobs/cnc-9"] = {
            "title": "CNC Machinist", "fingerprint": "old-fp-9",
            "listing_fingerprint": text_fingerprint("CNC Machinist"),
            "vanished_at": None,
        }
        conn = SyncConn(
            import_rows={
                f"{BASE}/jobs/cnc-9": {"id": "r9", "status": "published",
                                       "published_job_id": "job-9",
                                       "title": "CNC Machinist"},
            },
            career_jobs=stored,
        )
        source = {**SOURCE, "extraction_profile": _generic_profile()}
        _fetched, fake_get = _paged_fixture()

        for _ in range(2):
            with patch.object(cp, "_guarded_get", side_effect=fake_get), \
                 patch.object(cs, "check_apply_links", return_value={}):
                result = await run_pull(conn, source, triggered_by="user-1")

        assert result["removal_detection"] == "applied"
        assert result["jobs_removed"] == 1
        assert conn.import_rows[f"{BASE}/jobs/cnc-9"]["status"] == "stale"
        assert conn.career_jobs[f"{BASE}/jobs/cnc-9"]["vanished_at"] is not None

    async def test_failed_pull_stales_nothing(self):
        """Existing behaviour, pinned: a fetch that fails outright records the
        failure and touches no rows."""
        stored = _stored_for_listing()
        stored[f"{BASE}/jobs/electrician-1"]["consecutive_misses"] = 1
        conn = SyncConn(
            import_rows={
                f"{BASE}/jobs/electrician-1": {"id": "r1", "status": "published",
                                               "published_job_id": "job-1",
                                               "title": "Industrial Electrician"},
            },
            career_jobs=stored,
        )
        source = {**SOURCE, "extraction_profile": _generic_profile()}

        def boom(url, **kw):
            raise cp.httpx.ConnectError("boom")

        with patch.object(cp, "_guarded_get", side_effect=boom), \
             patch.object(cs, "scrape_career_source", return_value=("unknown", [])):
            result = await run_pull(conn, source, triggered_by="user-1")

        assert result["status"] == "no_jobs"
        assert result["jobs_removed"] == 0
        assert conn.import_rows[f"{BASE}/jobs/electrician-1"]["status"] == "published"
        assert conn.career_jobs[f"{BASE}/jobs/electrician-1"]["consecutive_misses"] == 1


class TestRemovalBlastRadiusGuard:
    def _mass_removal_conn(self):
        """42 live postings, 40 of them one miss from being staled, and a
        listing that only shows 3 — the shape of a scraper regression."""
        stored = _stored_for_listing()
        import_rows = {}
        for i in range(40):
            url = f"{BASE}/jobs/legacy-{i}"
            stored[url] = {
                "title": f"Legacy Role {i}", "fingerprint": f"fp-{i}",
                "listing_fingerprint": text_fingerprint(f"Legacy Role {i}"),
                "vanished_at": None, "consecutive_misses": 1,
            }
            import_rows[url] = {"id": f"r{i}", "status": "published",
                                "published_job_id": f"job-{i}",
                                "title": f"Legacy Role {i}"}
        return SyncConn(import_rows=import_rows, career_jobs=stored)

    async def test_guard_holds_the_removals_and_files_a_review_item(self):
        conn = self._mass_removal_conn()
        source = {**SOURCE, "extraction_profile": _generic_profile()}
        _fetched, fake_get = _paged_fixture()

        with patch.object(cp, "_guarded_get", side_effect=fake_get), \
             patch.object(cs, "check_apply_links", return_value={}):
            result = await run_pull(conn, source, triggered_by="user-1")

        assert result["listing_complete"] is True          # the crawl was fine
        assert result["removal_detection"] == "held_for_review"
        assert result["jobs_removed"] == 0
        assert conn.by_status("stale") == []               # nothing unpublished
        # Misses are not accrued either: the hold is a full stop, not a pause.
        assert all(r["consecutive_misses"] == 1 for u, r in conn.career_jobs.items()
                   if u.startswith(f"{BASE}/jobs/legacy-"))
        # One pending admin item, with the numbers in it.
        assert len(conn.review_items) == 1
        item = conn.review_items[0]
        assert item["item_type"] == "suspicious_import"
        assert item["entity_type"] == "career_source"
        assert "40 of 42" in item["description"]
        assert item["flags"]["would_remove"] == 40
        # Source parked for a human.
        assert conn.last_source_update[12] is True         # needs_attention
        assert "40 of 42" in conn.last_source_update[13]   # attention_reason
        assert "40 of 42" in result["details"]["removal_note"]

    async def test_repeated_holds_do_not_pile_up_review_items(self):
        conn = self._mass_removal_conn()
        source = {**SOURCE, "extraction_profile": _generic_profile()}
        _fetched, fake_get = _paged_fixture()

        for _ in range(3):
            with patch.object(cp, "_guarded_get", side_effect=fake_get), \
                 patch.object(cs, "check_apply_links", return_value={}):
                await run_pull(conn, source, triggered_by="user-1")

        assert len(conn.review_items) == 1

    async def test_a_clean_complete_sync_clears_the_park(self):
        conn = SyncConn(career_jobs=_stored_for_listing())
        source = {**SOURCE, "extraction_profile": _generic_profile()}
        _fetched, fake_get = _paged_fixture()

        with patch.object(cp, "_guarded_get", side_effect=fake_get), \
             patch.object(cs, "check_apply_links", return_value={}):
            await run_pull(conn, source, triggered_by="user-1")

        assert conn.last_source_update[12] is False        # needs_attention cleared
        assert conn.review_items == []

    async def test_a_failed_sync_leaves_an_existing_park_standing(self):
        conn = SyncConn(career_jobs=_stored_for_listing())
        source = {**SOURCE, "extraction_profile": _generic_profile()}

        def boom(url, **kw):
            raise cp.httpx.ConnectError("boom")

        with patch.object(cp, "_guarded_get", side_effect=boom), \
             patch.object(cs, "scrape_career_source", return_value=("unknown", [])):
            await run_pull(conn, source, triggered_by="user-1")

        assert conn.last_source_update[12] is None         # NULL = leave as-is
