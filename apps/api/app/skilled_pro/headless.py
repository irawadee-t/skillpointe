"""
headless.py — LISTING-ONLY headless fallback for JS-walled careers pages.

Some careers sites (Delta's Avature instance, Schneider's SPA) render their
job listings entirely client-side, so the plain-HTTP discovery path sees an
empty shell and honestly reports "no_jobs". This module renders JUST the
listing page in headless Chromium (Playwright), then hands the RENDERED DOM
to the exact same parsing pipeline the HTTP path uses (JSON-LD JobPosting
first, anchor-heuristic link discovery second). Detail pages are still
fetched over plain HTTP through the SSRF guard — headless is never used for
per-posting fetches.

Rules of engagement (enforced by the callers in worker/scheduler.py):
  * NEVER on the request path — scheduler/background only.
  * One page render per source per daily tick, with a tight timeout.
  * Gated on Settings.headless_scrape_enabled.
  * The SSRF guard validates the URL before the browser ever launches.

Everything here is sync (Playwright sync API) and must be called via
``asyncio.to_thread`` from async code — the sync API refuses to run on an
event-loop thread by design, which conveniently enforces the rule above.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.util.net_guard import validate_public_url

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_NAV_TIMEOUT_MS = 30_000     # page.goto budget
_SETTLE_MS = 3_500           # post-load settle so the SPA can paint listings
_SKIP_RESOURCES = {"image", "media", "font"}   # never needed for link discovery


def render_listing_html(url: str, *, timeout_ms: int = _NAV_TIMEOUT_MS,
                        settle_ms: int = _SETTLE_MS) -> Optional[str]:
    """Render one listing page in headless Chromium; return the DOM HTML.

    Returns None on any failure (missing Playwright, launch error, navigation
    timeout) — callers treat that exactly like an empty listing. The SSRF
    guard validates the URL first; heavy resources are blocked for speed.
    """
    validate_public_url(url)
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        logger.warning("Playwright not installed — headless fallback unavailable")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(
                    user_agent=_UA, viewport={"width": 1366, "height": 900},
                )
                page = ctx.new_page()
                page.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in _SKIP_RESOURCES
                    else route.continue_(),
                )
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                page.wait_for_timeout(settle_ms)
                return page.content()
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 — a render failure is a soft miss
        logger.warning("Headless render failed for %s: %s", url, exc)
        return None


def headless_careers_scrape(
    url: str, *, employer_name: str, max_jobs: int = 200,
    stats: Optional[dict[str, Any]] = None,
) -> list[Any]:
    """Headless-rendered listing → normal parsing pipeline → ScrapedJobs.

    Mirrors generic_careers_scrape exactly, except the LISTING HTML comes from
    the rendered DOM. Detail pages go through the standard guarded-HTTP
    parallel fetcher (JSON-LD → heuristic parse), so downstream quality is
    identical to the plain path.

    Only the FIRST rendered page is read, so the crawl reports itself complete
    (``stats["listing_complete"]``) only when the rendered listing shows no
    pagination at all. The caller must not detect removals otherwise.
    """
    from scraper.trades import classify  # type: ignore

    from app.skilled_pro.career_profile import _fetch_details_parallel
    from app.skilled_pro.career_sources import (
        _GENERIC_ANCHOR_TEXT,
        _bump,
        _looks_like_title,
        _mark_completeness,
        discover_job_links,
        discover_pagination_links,
        parse_jsonld_jobpostings,
    )

    _bump(stats, "headless_renders")
    html = render_listing_html(url)
    if not html:
        _mark_completeness(stats, complete=False, pages=0, reason="render_failed")
        return []
    paginated = bool(discover_pagination_links(html, url))
    _mark_completeness(stats, complete=not paginated, pages=1,
                       reason="headless_first_page" if paginated else None)

    # Path 1 — the rendered listing embeds full JobPosting JSON-LD.
    jobs = parse_jsonld_jobpostings(html, url, employer_name=employer_name)
    jobs = [j for j in jobs
            if j.source_url and j.source_url.rstrip("/") != url.rstrip("/")]
    if jobs:
        if stats is not None:
            stats["jsonld_listing"] = True
        return jobs[:max_jobs]

    # Path 2 — anchors from the rendered DOM, details over plain HTTP.
    links = discover_job_links(html, url)
    to_fetch: list[str] = []
    early = 0
    for link, anchor_text in links:
        text_l = (anchor_text or "").lower()
        if (
            anchor_text and len(anchor_text) >= 8
            and text_l not in _GENERIC_ANCHOR_TEXT
            and not classify(anchor_text).is_trade
            and _looks_like_title(anchor_text)
        ):
            early += 1
            continue
        to_fetch.append(link)
        if len(to_fetch) >= max_jobs:
            break
    _bump(stats, "early_rejected", early)
    return _fetch_details_parallel(to_fetch, url, employer_name=employer_name,
                                   stats=stats)
