"""New-partner ingestion mechanics: platform detection, slug locations,
queue debounce semantics. All network-free."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))


class TestCornerstoneDetection:
    def test_csod_host_detected(self):
        from scraper.platform import Platform, detect_from_url
        assert detect_from_url(
            "https://turnerconstruction.csod.com/ux/ats/careersite/4/home?c=turnerconstruction"
        ) == Platform.CORNERSTONE

    def test_parse_extracts_site_and_corp(self):
        from scraper.universal import _parse_cornerstone
        host, site, corp = _parse_cornerstone(
            "https://turnerconstruction.csod.com/ux/ats/careersite/4/home?c=turnerconstruction")
        assert (host, site, corp) == ("turnerconstruction.csod.com", 4, "turnerconstruction")

    def test_non_csod_not_matched(self):
        from scraper.universal import _parse_cornerstone
        assert _parse_cornerstone("https://careers.example.com/jobs") is None


class TestSuccessFactorsSlugLocation:
    def _loc(self, url):
        from app.skilled_pro.career_sources import _location_from_sf_slug
        return _location_from_sf_slug(url)

    def test_truncated_state_name(self):
        assert self._loc(
            "https://careers.huntingtoningalls.com/job/Newport-News-APPRENTICE-Virg/1322575400/"
        ) == ("Newport News", "VA")

    def test_percent_escapes_and_digits(self):
        assert self._loc(
            "https://x.com/job/Newport-News-EXPERIENCED-CNC-MACHINIST-WITH-UP-TO-%2410K-BONUS-Virg/1415347000/"
        ) == ("Newport News", "VA")

    def test_mississippi_prefix(self):
        assert self._loc("https://x.com/job/Pascagoula-WELDER-Missi/999/") == ("Pascagoula", "MS")

    def test_ambiguous_prefix_never_guesses_state(self):
        city, state = self._loc("https://x.com/job/Somewhere-THING-New/1/")
        assert state is None  # 'New' matches several states — must not guess

    def test_non_job_paths_ignored(self):
        assert self._loc("https://x.com/about/company/") == (None, None)


class TestFullStateNameBodyLine:
    def test_city_full_statename_line(self):
        from app.skilled_pro.career_sources import _location_from_page
        body = "Req ID: 1\nNewport News, Virginia\nFull-Time"
        assert _location_from_page(body, "https://x.com/j/1") == ("Newport News", "VA")

    def test_two_letter_still_wins(self):
        from app.skilled_pro.career_sources import _location_from_page
        body = "Carrollton, GA, US, 30119"
        assert _location_from_page(body, "https://x.com/j/1") == ("Carrollton", "GA")
