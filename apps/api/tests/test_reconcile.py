"""
test_reconcile.py — legacy-job → career-source URL matching (pure helpers).

The reconciliation script/endpoint enrolls pre-career-sources jobs into
fingerprint memory. These tests pin the matching ladder: learned link
patterns → listing host → Workday tenant host → registrable domain, and that
unrelated domains NEVER match (those jobs stay orphans under the tier-2
apply-link recheck).
"""
from __future__ import annotations

from app.skilled_pro.reconcile import job_matches_source, job_row_fingerprint


class TestJobMatchesSource:
    def test_learned_link_pattern_wins(self):
        profile = {"link_patterns": [
            r"^https?://jobs\.ball\.com/corp_packaging/[^/?#]+/[^/?#]+/[^/?#]+/?(?:[?#].*)?$"
        ]}
        assert job_matches_source(
            "https://jobs.ball.com/corp_packaging/job/Golden-Machinist-CO-80403/1401349300/",
            listing_url="https://jobs.ball.com/search/", profile=profile,
        )

    def test_exact_listing_host(self):
        assert job_matches_source(
            "https://careers.southwire.com/job/Carrollton-Welder-GA-30119/12345/",
            listing_url="https://careers.southwire.com/search/",
        )

    def test_workday_tenant_host(self):
        profile = {"platform_params": {"tenant": "acme", "wd": "wd5", "site": "External"}}
        assert job_matches_source(
            "https://acme.wd5.myworkdayjobs.com/en-US/External/job/Welder_R123",
            listing_url="https://careers.acme.com/jobs", profile=profile,
        )

    def test_registrable_domain_bridges_subdomains(self):
        # Listing on jobs.ball.com, posting URL on www.ball.com — same employer domain.
        assert job_matches_source(
            "https://www.ball.com/openings/production-tech-9",
            listing_url="https://jobs.ball.com/search/",
        )

    def test_unrelated_domain_never_matches(self):
        assert not job_matches_source(
            "https://careers.se.com/jobs/electrician-77",
            listing_url="https://jobs.ball.com/search/",
        )
        assert not job_matches_source(
            "https://evil.example.net/jobs/x",
            listing_url="https://careers.southwire.com/search/",
            profile={"link_patterns": [r"^https?://careers\.southwire\.com/job/.*$"]},
        )

    def test_garbage_urls_are_safe(self):
        assert not job_matches_source("not a url", listing_url="https://a.com/x")
        assert not job_matches_source("", listing_url="https://a.com/x")


class TestJobRowFingerprint:
    def test_stable_and_content_sensitive(self):
        row = {"title_raw": "Welder I", "description_raw": "Weld things",
               "city": "Carrollton", "state": "GA"}
        assert job_row_fingerprint(row) == job_row_fingerprint(dict(row))
        changed = {**row, "description_raw": "Weld MORE things"}
        assert job_row_fingerprint(row) != job_row_fingerprint(changed)
