"""
career_sources.py — Employer self-serve careers-page pull pipeline.

An employer connects a careers-page URL once (employer_career_sources). Every
pull re-scrapes that URL and syncs the results into the source's rolling
job_import_batches batch:

  1. Platform detection first (Workday / Greenhouse / Lever JSON APIs via
     packages/scraper/universal.py — the highest-quality path).
  2. Generic fallback for unknown platforms: fetch the page through the SSRF
     guard, parse schema.org JobPosting JSON-LD (best generic signal), then
     anchor-heuristic link discovery + per-posting fetches.
  3. Skilled-trades filter via packages/scraper/trades.py (rejected roles are
     counted for transparency, never silently vanish).
  4. Apply-link validation (HEAD→GET through the SSRF guard, tight timeouts);
     broken links flag the row instead of publishing silently.
  5. Dedupe on (batch_id, source_url): existing rows update in place, new rows
     insert, vanished rows go 'stale' (published ones deactivate the live job).

Everything network-bound is sync (called via asyncio.to_thread from the
router); the DB sync helpers are async. No LLM required anywhere — the unified
"headers" come from the deterministic job_display_sections parser downstream.
"""
from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

# Triggers the packages/ sys.path bootstrap as a side effect.
from app.skilled_pro.job_imports import universal_scrape  # noqa: F401
from app.util.net_guard import BlockedURLError, safe_get_sync, validate_public_url

logger = logging.getLogger(__name__)

# Repo-standard timeouts: connect 5s / read 30s, 1 retry.
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_MAX_LINK_CHECKS = 100          # per pull — keeps a big board from stalling the run
_LINK_CHECK_WORKERS = 8
_DETAIL_FETCH_DELAY = 0.25      # polite delay between generic detail fetches

_GENERIC_TITLE_STRIP = re.compile(r"\s*[|\-–—]\s*(?:careers?|jobs?)\b.*$", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Human copy for pull outcomes. Status codes stay machine-readable
# (ok | blocked | no_jobs | error) but every stored/returned `error` string is
# a sentence a non-technical employer can act on. Raw engineering detail
# (exception text, guard internals) is logged, never stored or returned.
# ---------------------------------------------------------------------------
HUMAN_ERRORS = {
    "blocked": "We can't reach that address. Use your public careers page URL.",
    "no_jobs": (
        "We couldn't find any job postings at this page. If your jobs are "
        "listed on a different page, connect that one instead."
    ),
    "error": (
        "Something went wrong while reading this page. Try again in a few "
        "minutes. If it keeps failing, try a different page or the CSV upload."
    ),
}


# ============================================================================
# JSON-LD JobPosting parsing (pure — unit-tested)
# ============================================================================

_JSONLD_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def _iter_jsonld_objects(html: str):
    """Yield every decoded JSON-LD object in the page (flattening @graph)."""
    for m in _JSONLD_RE.finditer(html or ""):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        for obj in stack:
            if not isinstance(obj, dict):
                continue
            graph = obj.get("@graph")
            if isinstance(graph, list):
                yield from (g for g in graph if isinstance(g, dict))
            yield obj


def _jsonld_type(obj: dict) -> str:
    t = obj.get("@type")
    if isinstance(t, list):
        t = t[0] if t else ""
    return str(t or "")


def _jobposting_location(obj: dict) -> tuple[Optional[str], Optional[str]]:
    loc = obj.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if not isinstance(loc, dict):
        return None, None
    addr = loc.get("address")
    if isinstance(addr, list):
        addr = addr[0] if addr else None
    if not isinstance(addr, dict):
        return None, None
    from scraper.base import normalize_state  # type: ignore

    city = addr.get("addressLocality") or None
    state = normalize_state(addr.get("addressRegion")) if addr.get("addressRegion") else None
    return city, state


def _jobposting_pay(obj: dict) -> Optional[str]:
    sal = obj.get("baseSalary")
    if not isinstance(sal, dict):
        return None
    val = sal.get("value")
    unit = None
    if isinstance(val, dict):
        unit = val.get("unitText")
        mn, mx = val.get("minValue"), val.get("maxValue")
        single = val.get("value")
        if mn is not None or mx is not None:
            lo = f"${mn:,.0f}" if isinstance(mn, (int, float)) else None
            hi = f"${mx:,.0f}" if isinstance(mx, (int, float)) else None
            txt = " - ".join(x for x in (lo, hi) if x)
        elif isinstance(single, (int, float)):
            txt = f"${single:,.0f}"
        else:
            return None
    elif isinstance(val, (int, float)):
        txt = f"${val:,.0f}"
    else:
        return None
    if unit:
        txt = f"{txt} per {str(unit).lower()}"
    return txt


def parse_jsonld_jobpostings(html: str, page_url: str, *, employer_name: str) -> list[Any]:
    """Extract schema.org JobPosting objects from a page as ScrapedJobs.

    Returns [] when the page carries no JobPosting JSON-LD. The posting's own
    `url` (fallback: the fetched page URL) becomes source_url — always the
    canonical posting URL, never the careers root.
    """
    from scraper.base import ScrapedJob, strip_html  # type: ignore

    site = f"careers:{urlparse(page_url).hostname or 'unknown'}"
    out: list[Any] = []
    for obj in _iter_jsonld_objects(html):
        if _jsonld_type(obj).lower() != "jobposting":
            continue
        title = str(obj.get("title") or "").strip()
        if not title:
            continue
        url = obj.get("url") or obj.get("sameAs") or page_url
        if isinstance(url, dict):
            url = url.get("@id") or page_url
        url = urljoin(page_url, str(url))
        city, state = _jobposting_location(obj)
        emp_type = obj.get("employmentType")
        if isinstance(emp_type, list):
            emp_type = emp_type[0] if emp_type else None
        ident = obj.get("identifier")
        if isinstance(ident, dict):
            ident = ident.get("value")
        posted = str(obj.get("datePosted") or "")[:10] or None
        out.append(
            ScrapedJob(
                title=title,
                employer_name=employer_name,
                source_url=url,
                source_site=site,
                city=city,
                state=state,
                description=strip_html(str(obj.get("description") or "")) or None,
                pay_raw=_jobposting_pay(obj),
                posted_date=posted,
                employment_type=str(emp_type) if emp_type else None,
                req_id=str(ident) if ident else None,
            )
        )
    return out


# ============================================================================
# Anchor-heuristic job-link discovery (pure — unit-tested)
# ============================================================================

_JOB_HREF_HINT = re.compile(
    r"(?:/jobs?/|/careers?/[^/?#]+|/openings?/|/positions?/|/vacanc|/posting/|"
    r"/opportunit|[?&]gh_jid=|/job-details?/|/jobdetails?/|/requisition)",
    re.IGNORECASE,
)
_SKIP_HREF = re.compile(
    r"^(?:mailto:|tel:|javascript:|#)|\.(?:pdf|png|jpe?g|svg|css|js)(?:[?#]|$)|"
    r"/(?:login|signin|search|faq|benefits|about|privacy|terms|contact)(?:[/?#]|$)|"
    # Listing pagination is never a job posting: /jobs/page/10, ?page=3,
    # ?page_number=2, ?startrow=25, ?offset=50 …
    r"/pages?/\d+(?:[/?#]|$)|[?&](?:page|page_number|pg|offset|startrow)=\d+",
    re.IGNORECASE,
)
_GENERIC_ANCHOR_TEXT = {
    "apply", "apply now", "view job", "view all jobs", "learn more", "details",
    "read more", "see job", "view", "more", "job details",
}


def discover_job_links(html: str, base_url: str, *, max_links: int = 200) -> list[tuple[str, str]]:
    """Find likely job-posting links on a careers page.

    Returns [(absolute_url, anchor_text)] — deduped, same-site-or-known-ATS
    only, never the page itself. Heuristic by design; the trades classifier and
    per-posting parse downstream do the precise filtering.
    """
    from bs4 import BeautifulSoup
    from scraper.platform import Platform, detect_from_url  # type: ignore

    soup = BeautifulSoup(html or "", "html.parser")
    base_host = (urlparse(base_url).hostname or "").lower()
    base_root = _registrable(base_host)
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or _SKIP_HREF.search(href):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        host = (parsed.hostname or "").lower()
        # Same registrable domain, or a known ATS host (vanity page linking out
        # to its Workday/Greenhouse/Lever board). Arbitrary third-party
        # domains never qualify.
        if _registrable(host) != base_root and detect_from_url(absolute) == Platform.UNKNOWN:
            continue
        if not _JOB_HREF_HINT.search(parsed.path + ("?" + parsed.query if parsed.query else "")):
            continue
        clean = absolute.split("#", 1)[0]
        if clean.rstrip("/") == base_url.rstrip("/") or clean in seen:
            continue
        seen.add(clean)
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        out.append((clean, text))
        if len(out) >= max_links:
            break
    return out


def _registrable(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


# ============================================================================
# Listing pagination (pure discovery + a bounded crawl loop)
# ============================================================================
#
# discover_job_links deliberately SKIPS pagination hrefs — they are never job
# postings. But the listing has to be walked to its END before the absence of a
# posting means anything: a first-page-only crawl says "removed" about every
# posting below the fold. These two helpers walk the pages, under a hard bound,
# and report honestly whether the walk reached the end.

MAX_LISTING_PAGES = 40      # hard bound on pages walked per listing crawl
MAX_LISTING_JOBS = 2000     # hard bound on postings collected per listing crawl

# The mirror image of the pagination clause in _SKIP_HREF: /jobs/page/3,
# ?page=2, ?startrow=25, ?offset=50, ?from=20 …
_PAGINATION_HREF = re.compile(
    r"/pages?/\d+(?:[/?#]|$)|[?&](?:page|page_number|pg|offset|startrow|from|start)=\d+",
    re.IGNORECASE,
)


def discover_pagination_links(html: str, base_url: str, *,
                              max_links: int = MAX_LISTING_PAGES) -> list[str]:
    """Find "next page" / numbered-page links for THIS listing.

    Same-path-same-host only: a pagination link differs from the page it sits
    on by its page/offset parameter, never by its path root. That keeps the
    crawl inside the listing instead of wandering the site.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    base = urlparse(base_url)
    base_host = (base.hostname or "").lower()
    seen: set[str] = set()
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(base_url, href).split("#", 1)[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if (parsed.hostname or "").lower() != base_host:
            continue
        if not _PAGINATION_HREF.search(
            parsed.path + ("?" + parsed.query if parsed.query else "")
        ):
            continue
        if absolute.rstrip("/") == base_url.rstrip("/") or absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
        if len(out) >= max_links:
            break
    return out


def crawl_listing_pages(
    first_url: str, first_html: str, fetch_html, *,
    max_pages: int = MAX_LISTING_PAGES,
) -> tuple[list[tuple[str, str]], bool, Optional[str]]:
    """Walk a paginated listing from its first (already-fetched) page.

    ``fetch_html(url) -> str | None`` fetches one more listing page; None means
    the fetch failed. Returns (pages, complete, incomplete_reason) where
    ``pages`` is [(url, html)] including the first, and ``complete`` is True
    only when every discovered page was fetched and no bound was hit.

    Sites that expose only a "next" link are walked one hop at a time; sites
    with numbered pagination enqueue every page from the first one.
    """
    pages: list[tuple[str, str]] = [(first_url, first_html)]
    seen = {first_url.rstrip("/")}
    queue: list[str] = []

    def enqueue(html: str, page_url: str) -> None:
        for link in discover_pagination_links(html, page_url):
            if link.rstrip("/") not in seen:
                seen.add(link.rstrip("/"))
                queue.append(link)

    enqueue(first_html, first_url)
    while queue:
        if len(pages) >= max_pages:
            return pages, False, "page_bound"
        nxt = queue.pop(0)
        html = fetch_html(nxt)
        if html is None:
            # A page we know exists but could not read: the listing we hold is
            # provably partial, so removal detection must not run on it.
            return pages, False, "page_fetch_failed"
        pages.append((nxt, html))
        enqueue(html, nxt)
    return pages, True, None


# ============================================================================
# Generic careers-page scrape (network — SSRF-guarded)
# ============================================================================

def _bump(stats: Optional[dict[str, Any]], key: str, by: int = 1) -> None:
    if stats is not None:
        stats[key] = stats.get(key, 0) + by


def _mark_completeness(stats: Optional[dict[str, Any]], *, complete: bool,
                       pages: int, reason: Optional[str]) -> None:
    """Record whether the listing crawl saw the whole site (see run_pull)."""
    if stats is None:
        return
    stats["listing_complete"] = bool(complete)
    stats["listing_pages"] = pages
    if reason:
        stats["incomplete_reason"] = reason


def generic_careers_scrape(
    url: str, *, employer_name: str, max_jobs: int = 200,
    stats: Optional[dict[str, Any]] = None,
) -> list[Any]:
    """Fallback scraper for careers pages on no recognized ATS.

    JSON-LD JobPosting on the listing page wins outright; otherwise discover
    job links, fetch each posting (through the SSRF guard), and parse JSON-LD
    or headline/body heuristics per posting.

    When ``stats`` is passed, anchors skipped as clearly-non-trades titles are
    counted under ``stats["early_rejected"]`` so pull history stays honest,
    every HTTP request bumps ``stats["fetches"]``, and structure signals for
    the learned profile land in ``stats["jsonld_listing"]`` /
    ``stats["listing_etag"]`` / ``stats["listing_last_modified"]``.

    The listing is walked to its LAST page (bounded). Whether the walk actually
    reached the end lands in ``stats["listing_complete"]`` (+ ``listing_pages``
    and ``incomplete_reason``) — the caller must not run removal detection on
    an incomplete crawl.
    """
    from scraper.base import ScrapedJob, strip_html  # type: ignore
    from scraper.extract import parse_sections  # type: ignore
    from scraper.trades import classify  # type: ignore

    try:
        _bump(stats, "fetches")
        page = safe_get_sync(url, timeout=_TIMEOUT, headers={"User-Agent": _UA})
    except (BlockedURLError, httpx.HTTPError) as exc:
        logger.warning("Generic scrape could not fetch %s: %s", url, exc)
        _mark_completeness(stats, complete=False, pages=0, reason="listing_fetch_failed")
        return []
    html = page.text
    if stats is not None:
        headers = getattr(page, "headers", {}) or {}
        if headers.get("etag"):
            stats["listing_etag"] = headers.get("etag")
        if headers.get("last-modified"):
            stats["listing_last_modified"] = headers.get("last-modified")

    def fetch_page(page_url: str) -> Optional[str]:
        try:
            _bump(stats, "fetches")
            resp = safe_get_sync(page_url, timeout=_TIMEOUT, headers={"User-Agent": _UA})
        except (BlockedURLError, httpx.HTTPError):
            return None
        return resp.text if resp.status_code < 400 else None

    pages, complete, reason = crawl_listing_pages(url, html, fetch_page)

    # Path 1 — the listing pages embed full JobPosting JSON-LD.
    jobs: list[Any] = []
    seen_urls: set[str] = set()
    for page_url, page_html in pages:
        for j in parse_jsonld_jobpostings(page_html, page_url, employer_name=employer_name):
            if not j.source_url or j.source_url.rstrip("/") == url.rstrip("/"):
                continue
            if j.source_url in seen_urls:
                continue
            seen_urls.add(j.source_url)
            jobs.append(j)
    if jobs:
        if stats is not None:
            stats["jsonld_listing"] = True
        if len(jobs) > max_jobs:
            complete, reason = False, "max_jobs_cap"
        _mark_completeness(stats, complete=complete, pages=len(pages), reason=reason)
        return jobs[:max_jobs]

    # Path 2 — anchor discovery + per-posting fetch.
    links: list[tuple[str, str]] = []
    seen_links: set[str] = set()
    for page_url, page_html in pages:
        for link, text in discover_job_links(page_html, page_url):
            if link not in seen_links:
                seen_links.add(link)
                links.append((link, text))
    if len(links) > MAX_LISTING_JOBS:
        complete, reason = False, "job_bound"
        links = links[:MAX_LISTING_JOBS]
    if len(links) > max_jobs:
        complete, reason = False, "max_jobs_cap"
    _mark_completeness(stats, complete=complete, pages=len(pages), reason=reason)
    out: list[Any] = []
    site = f"careers:{urlparse(url).hostname or 'unknown'}"
    for link, anchor_text in links:
        if len(out) >= max_jobs:
            break
        # Cheap early skip: anchor text that clearly reads as a non-trades
        # title (only when it's a real title, not "View job" chrome).
        text_l = anchor_text.lower()
        if (
            anchor_text
            and len(anchor_text) >= 8
            and text_l not in _GENERIC_ANCHOR_TEXT
            and not classify(anchor_text).is_trade
            and _looks_like_title(anchor_text)
        ):
            _bump(stats, "early_rejected")
            continue
        try:
            time.sleep(_DETAIL_FETCH_DELAY)
            _bump(stats, "fetches")
            resp = safe_get_sync(link, timeout=_TIMEOUT, headers={"User-Agent": _UA})
            if resp.status_code >= 400:
                continue
        except (BlockedURLError, httpx.HTTPError):
            continue
        detail_html = resp.text
        # Detail-page JSON-LD is still the best-quality parse.
        detail_jobs = parse_jsonld_jobpostings(detail_html, link, employer_name=employer_name)
        if detail_jobs:
            job = detail_jobs[0]
            job.source_url = link  # canonical posting URL the user landed on
            out.append(job)
            continue
        title, body = _extract_title_and_body(detail_html)
        if not title:
            continue
        parsed = parse_sections(body)
        city, state = _location_from_page(body, link)
        out.append(
            ScrapedJob(
                title=title,
                employer_name=employer_name,
                source_url=link,
                source_site=site,
                city=city,
                state=state,
                description=parsed.description or strip_html(body),
                responsibilities=parsed.responsibilities,
                requirements=parsed.requirements,
                qualifications=parsed.qualifications,
                pay_raw=parsed.pay_raw,
                experience_level=parsed.experience_level,
            )
        )
    return out


# "City, ST" (optionally ", US, 30119") near the top of a posting page.
_CITY_STATE_LINE = re.compile(r"^([A-Z][\w .'\-]{1,40}),\s*([A-Z]{2})(?:\b|,)")
# Full state names too: SuccessFactors sites commonly render
# "Newport News, Virginia" — a 2-letter-only pattern left every HII posting
# location-less (2026-08 audit), and a job without a state matches nobody.
_CITY_STATENAME_LINE = re.compile(r"^([A-Z][\w .'\-]{1,40}),\s*([A-Za-z ]{4,25})(?:,|$)")
# ATS URL slugs often carry "-ST-ZIP" ("/job/Carrollton-Welder-GA-30119/123/").
_URL_STATE_RE = re.compile(r"-([A-Z]{2})-\d{4,5}(?:/|$)")


def _location_from_page(body: Optional[str], url: str) -> tuple[Optional[str], Optional[str]]:
    """Deterministic city/state fallback for heuristic detail parses: a
    "City, ST" or "City, StateName" line near the top of the page, else a
    state code in the URL."""
    from scraper.base import US_STATE_ABBRS, normalize_state  # type: ignore

    for line in (body or "").split("\n")[:20]:
        stripped = line.strip()
        m = _CITY_STATE_LINE.match(stripped)
        if m and m.group(2) in US_STATE_ABBRS:
            return m.group(1).strip(), m.group(2)
        m = _CITY_STATENAME_LINE.match(stripped)
        if m:
            st = normalize_state(m.group(2).strip())
            if st:
                return m.group(1).strip(), st
    m = _URL_STATE_RE.search(urlparse(url).path)
    if m and m.group(1) in US_STATE_ABBRS:
        return None, m.group(1)
    return _location_from_sf_slug(url)


def _location_from_sf_slug(url: str) -> tuple[Optional[str], Optional[str]]:
    """SuccessFactors slug fallback: /job/Newport-News-SOME-TITLE-Virg/123/.

    The slug leads with the city in Title-Case tokens and ends with a
    TRUNCATED full state name ("Virg" for Virginia) — neither a "City, ST"
    body line nor a 2-letter URL code exists, which left every HII posting
    location-less (2026-08). City = leading Titlecase tokens (stopping at the
    first ALL-CAPS title token); state = unique full-name prefix match of the
    trailing token, 4+ chars so "Virg" resolves but "New" never guesses.
    """
    from scraper.base import US_STATE_FULL_TO_ABBR  # type: ignore

    # Slug tokens may include digits and %-escapes ("UP-TO-%2410K-BONUS",
    # "2026-HIGH-SCHOOL-SENIORS") — accept them; token logic filters below.
    m = re.search(r"/job/([A-Za-z][A-Za-z0-9%-]+)/\d+/?$", urlparse(url).path)
    if not m:
        return None, None
    tokens = [t for t in m.group(1).split("-") if t]
    if len(tokens) < 3:
        return None, None

    state = None
    tail = tokens[-1].lower()
    if len(tail) >= 4:
        hits = {abbr for name, abbr in US_STATE_FULL_TO_ABBR.items()
                if name.split()[0].startswith(tail) or name.replace(" ", "").startswith(tail)}
        if len(hits) == 1:
            state = next(iter(hits))

    city_tokens: list[str] = []
    for t in tokens:
        # Title-Case tokens before the first ALL-CAPS/lower token are the city.
        if t[0].isupper() and not t.isupper() and t[1:].islower():
            city_tokens.append(t)
            if len(city_tokens) >= 3:
                break
        else:
            break
    city = " ".join(city_tokens) if city_tokens else None
    if state is None and city is None:
        return None, None
    return city, state


def _looks_like_title(text: str) -> bool:
    """True when anchor text reads like a job title (vs. navigation chrome)."""
    words = text.split()
    return 1 < len(words) <= 10 and not text.endswith("…")


# Page chrome that pollutes scraped descriptions (cookie banners, consent
# managers, share widgets, breadcrumbs). Matched against id/class attributes.
_NOISE_ATTR_RE = re.compile(
    r"cookie|consent|onetrust|truste|gdpr|breadcrumb|share|social|banner|"
    r"subscribe|newsletter|sidebar|similar-jobs|related-jobs|jobalert|talent-?community",
    re.IGNORECASE,
)

# Likely job-description containers, most specific first.
_BODY_SELECTORS = (
    "[class*=jobdescription]", "[class*=job-description]", "[class*=jobDescription]",
    "[class*=job-details]", "[class*=jobDetails]", "[id*=job-description]",
    "[id*=jobDescription]", "article", "main",
)


def _extract_title_and_body(html: str) -> tuple[Optional[str], Optional[str]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript",
                     "form", "button", "iframe"]):
        tag.decompose()
    for tag in soup.find_all(attrs={"class": _NOISE_ATTR_RE}):
        tag.decompose()
    for tag in soup.find_all(attrs={"id": _NOISE_ATTR_RE}):
        tag.decompose()
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else None
    if not title and soup.title:
        title = _GENERIC_TITLE_STRIP.sub("", soup.title.get_text(strip=True)).strip() or None
    container = None
    for sel in _BODY_SELECTORS:
        try:
            found = soup.select_one(sel)
        except Exception:
            found = None
        # A real description container has substantial text.
        if found and len(found.get_text(strip=True)) > 400:
            container = found
            break
    if container is None:
        container = soup.body or soup
    body = container.get_text("\n", strip=True) if container else None
    return title, body


# ============================================================================
# Skilled-trades filter (consumes packages/scraper/trades.py — do not edit it)
# ============================================================================

def filter_trades(jobs: list[Any]) -> tuple[list[Any], int]:
    """Keep skilled-trades roles; return (kept, rejected_count). Sets
    job_category to the canonical trade family when the classifier finds one."""
    from scraper.trades import classify  # type: ignore

    kept: list[Any] = []
    rejected = 0
    for j in jobs:
        match = classify(j.title, j.description)
        if not match.is_trade:
            rejected += 1
            continue
        if match.family and not j.job_category:
            j.job_category = match.family
        kept.append(j)
    return kept, rejected


# ============================================================================
# Apply-link validation (SSRF-guarded, HEAD → GET, 1 retry)
# ============================================================================

def check_apply_link(url: str) -> str:
    """Validate an apply/source URL. Returns 'ok' | 'broken' | 'blocked'.

    Goes through the SSRF guard first (user-supplied URL); every redirect hop
    is re-validated. HEAD is tried first; inconclusive statuses fall back to a
    GET because many ATSs reject HEAD from non-browsers.
    """
    try:
        validate_public_url(url)
    except BlockedURLError:
        return "blocked"
    except Exception:
        return "broken"

    for _attempt in range(2):  # 1 retry
        try:
            status = _status_with_safe_redirects(url, method="HEAD")
            if status in (403, 405, 429, 501) or status >= 500:
                status = _status_with_safe_redirects(url, method="GET")
            return "ok" if status < 400 else "broken"
        except BlockedURLError:
            return "blocked"
        except httpx.HTTPError:
            continue
        except Exception:
            continue
    return "broken"


def _status_with_safe_redirects(url: str, *, method: str, max_redirects: int = 4) -> int:
    current = url
    with httpx.Client(follow_redirects=False, timeout=_TIMEOUT,
                      headers={"User-Agent": _UA}) as client:
        for _ in range(max_redirects + 1):
            validate_public_url(current)
            resp = client.request(method, current)
            if resp.is_redirect and resp.headers.get("location"):
                current = str(resp.next_request.url) if resp.next_request else urljoin(
                    current, resp.headers["location"])
                continue
            return resp.status_code
    return 599  # too many redirects


def check_apply_links(urls: list[str]) -> dict[str, str]:
    """Concurrently validate a batch of apply links (capped)."""
    targets = list(dict.fromkeys(u for u in urls if u))[:_MAX_LINK_CHECKS]
    if not targets:
        return {}
    with ThreadPoolExecutor(max_workers=_LINK_CHECK_WORKERS) as pool:
        results = pool.map(check_apply_link, targets)
    return dict(zip(targets, results))


# ============================================================================
# Sync planning (pure — unit-tested)
# ============================================================================

def plan_sync(existing: dict[str, str], fresh_urls: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Decide the fate of each source_url on a re-pull.

    existing: {source_url: row_status} already in the rolling batch.
    Returns (new_urls, update_urls, stale_urls). 'excluded' and 'rejected'
    rows are the employer's/admin's explicit call — they never resurrect and
    never go stale.
    """
    fresh = list(dict.fromkeys(fresh_urls))
    fresh_set = set(fresh)
    new_urls = [u for u in fresh if u not in existing]
    update_urls = [u for u in fresh if u in existing and existing[u] not in ("excluded", "rejected")]
    stale_urls = [
        u for u, st in existing.items()
        if u not in fresh_set and st in ("staged", "published")
    ]
    return new_urls, update_urls, stale_urls


# ============================================================================
# DB sync + pull orchestration (async)
# ============================================================================

_ROW_COLS = (
    "title_raw", "description_raw", "responsibilities_raw", "requirements_raw",
    "preferred_qualifications_raw", "city", "state", "country", "work_setting",
    "pay_raw", "experience_level", "employment_type", "req_id", "job_category",
    "posted_date",
)


def _job_to_row(j: Any) -> dict[str, Any]:
    return {
        "title_raw": j.title,
        "description_raw": j.description,
        "responsibilities_raw": j.responsibilities,
        "requirements_raw": j.requirements,
        "preferred_qualifications_raw": j.qualifications,
        "city": j.city,
        "state": j.state,
        "country": j.country or "US",
        "work_setting": j.work_setting,
        "pay_raw": j.pay_raw,
        "experience_level": j.experience_level,
        "employment_type": j.employment_type,
        "req_id": j.req_id,
        "job_category": j.job_category,
        "posted_date": j.posted_date,
        "source_url": j.source_url,
    }


_DETAIL_TITLES_CAP = 25   # max job titles listed per event in the activity log


def _title_entry(title: Optional[str], url: Optional[str]) -> dict[str, Any]:
    return {"title": title or "Untitled role", "url": url}


async def sync_jobs_into_batch(
    conn, batch_id: str, jobs: list[Any], link_results: dict[str, str],
) -> dict[str, int]:
    """Back-compat wrapper around ``sync_rows`` — counters only."""
    counters, _details = await sync_rows(conn, batch_id, jobs, link_results)
    return counters


async def sync_rows(
    conn, batch_id: str, jobs: list[Any], link_results: dict[str, str],
    *, present_urls: Optional[set[str]] = None,
) -> tuple[dict[str, int], dict[str, Any]]:
    """Dedupe-sync scraped jobs into the rolling batch.

    Existing rows (matched on source_url) update in place; new rows insert as
    'staged'; vanished rows flip to 'stale' (published ones also deactivate the
    live job so dead postings never rank).

    ``present_urls`` is the FULL set of job URLs currently live on the site.
    On incremental syncs ``jobs`` carries only the new/changed postings, so
    staleness is judged against ``present_urls`` — unchanged rows are left
    completely untouched (and a previously-stale row whose URL reappears
    unchanged is revived). Defaults to the jobs' own URLs (full-pull shape).

    Returns (counters, details) where details carries the human-readable event
    payload: added/updated/removed/held job titles + the unchanged count.
    """
    existing_rows = await conn.fetch(
        "SELECT id, source_url, status::text AS status, published_job_id, title_raw "
        "FROM public.job_import_rows WHERE batch_id = $1::uuid AND source_url IS NOT NULL",
        batch_id,
    )
    existing = {r["source_url"]: r["status"] for r in existing_rows}
    by_url = {r["source_url"]: r for r in existing_rows}
    jobs_by_url = {j.source_url: j for j in jobs if j.source_url}
    present = set(present_urls) if present_urls is not None else set(jobs_by_url)
    present |= set(jobs_by_url)   # fetched jobs are on the site by definition

    new_urls, update_urls, _ = plan_sync(existing, list(jobs_by_url.keys()))
    stale_urls = [
        u for u, st in existing.items()
        if u not in present and st in ("staged", "published")
    ]
    # Reappeared unchanged: stale rows whose URL is live again but content
    # didn't change (no re-fetch happened) — revive without rewriting content.
    revive_urls = [
        u for u, st in existing.items()
        if st == "stale" and u in present and u not in jobs_by_url
    ]
    details: dict[str, Any] = {
        "added": [], "updated": [], "removed": [], "held": [], "restored": [],
    }
    broken = 0

    for url in new_urls:
        row = _job_to_row(jobs_by_url[url])
        link_status = link_results.get(url)
        if link_status in ("broken", "blocked"):
            broken += 1
            details["held"].append(_title_entry(row["title_raw"], url))
        details["added"].append(_title_entry(row["title_raw"], url))
        await conn.execute(
            """
            INSERT INTO public.job_import_rows
                (batch_id, title_raw, description_raw, responsibilities_raw,
                 requirements_raw, preferred_qualifications_raw,
                 city, state, country, work_setting, pay_raw,
                 experience_level, employment_type, req_id, job_category,
                 posted_date, source_url, link_status, link_checked_at)
            VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18::text,
                    CASE WHEN $18::text IS NULL THEN NULL ELSE now() END)
            ON CONFLICT (batch_id, source_url) WHERE source_url IS NOT NULL DO NOTHING
            """,
            batch_id, *(row[c] for c in _ROW_COLS), row["source_url"], link_status,
        )

    for url in update_urls:
        row = _job_to_row(jobs_by_url[url])
        rec = by_url[url]
        link_status = link_results.get(url)
        if link_status in ("broken", "blocked"):
            broken += 1
            details["held"].append(_title_entry(row["title_raw"], url))
        details["updated"].append(_title_entry(row["title_raw"], url))
        # A stale row whose posting returned goes back to review ('staged') —
        # unless it was already published, in which case it stays published and
        # the live job reactivates below.
        was = rec["status"]
        next_status = was
        if was == "stale":
            next_status = "published" if rec["published_job_id"] else "staged"
        await conn.execute(
            """
            UPDATE public.job_import_rows SET
                title_raw=$2, description_raw=$3, responsibilities_raw=$4,
                requirements_raw=$5, preferred_qualifications_raw=$6,
                city=$7, state=$8, country=$9, work_setting=$10, pay_raw=$11,
                experience_level=$12, employment_type=$13, req_id=$14,
                job_category=$15, posted_date=$16,
                status=$17::job_import_row_status_enum,
                link_status=COALESCE($18::text, link_status),
                link_checked_at=CASE WHEN $18::text IS NULL THEN link_checked_at ELSE now() END,
                updated_at=now()
            WHERE id = $1::uuid
            """,
            str(rec["id"]), *(row[c] for c in _ROW_COLS), next_status, link_status,
        )
        if rec["published_job_id"]:
            # Refresh the live job from the same canonical source (content
            # refresh of an already-approved posting, not a new publication).
            await conn.execute(
                """
                UPDATE public.jobs SET
                    title_raw=$2, description_raw=$3, responsibilities_raw=$4,
                    requirements_raw=$5, preferred_qualifications_raw=$6,
                    city=$7, state=$8, pay_raw=$9, experience_level=$10,
                    is_active=TRUE, last_verified_at=now(),
                    apply_link_status=COALESCE($11::text, apply_link_status),
                    apply_link_checked_at=CASE WHEN $11::text IS NULL THEN apply_link_checked_at ELSE now() END,
                    updated_at=now()
                WHERE id = $1::uuid
                """,
                str(rec["published_job_id"]),
                row["title_raw"], row["description_raw"], row["responsibilities_raw"],
                row["requirements_raw"], row["preferred_qualifications_raw"],
                row["city"], row["state"], row["pay_raw"], row["experience_level"],
                link_status,
            )

    for url in stale_urls:
        rec = by_url[url]
        details["removed"].append(
            _title_entry(rec["title_raw"] if "title_raw" in _rec_keys(rec) else None, url))
        await conn.execute(
            "UPDATE public.job_import_rows SET status='stale', updated_at=now() WHERE id=$1::uuid",
            str(rec["id"]),
        )
        if rec["published_job_id"]:
            await conn.execute(
                "UPDATE public.jobs SET is_active=FALSE, updated_at=now() WHERE id=$1::uuid",
                str(rec["published_job_id"]),
            )

    for url in revive_urls:
        rec = by_url[url]
        next_status = "published" if rec["published_job_id"] else "staged"
        details["restored"].append(
            _title_entry(rec["title_raw"] if "title_raw" in _rec_keys(rec) else None, url))
        await conn.execute(
            "UPDATE public.job_import_rows SET status=$2::job_import_row_status_enum, "
            "updated_at=now() WHERE id=$1::uuid",
            str(rec["id"]), next_status,
        )
        if rec["published_job_id"]:
            await conn.execute(
                "UPDATE public.jobs SET is_active=TRUE, last_verified_at=now(), "
                "updated_at=now() WHERE id=$1::uuid",
                str(rec["published_job_id"]),
            )

    # Keep the batch's staged counter accurate.
    await conn.execute(
        "UPDATE public.job_import_batches SET rows_total = "
        "(SELECT count(*) FROM public.job_import_rows WHERE batch_id = $1::uuid AND status = 'staged'), "
        "updated_at = now() WHERE id = $1::uuid",
        batch_id,
    )
    # Unchanged = rows that are live on the site and were not rewritten.
    details["unchanged"] = max(
        0,
        len([u for u, st in existing.items() if u in present and st not in ("excluded", "rejected")])
        - len(update_urls) - len(revive_urls),
    )
    for key in ("added", "updated", "removed", "held", "restored"):
        overflow = len(details[key]) - _DETAIL_TITLES_CAP
        if overflow > 0:
            details[key] = details[key][:_DETAIL_TITLES_CAP]
            details[f"{key}_more"] = overflow
        if not details[key]:
            del details[key]
    counters = {
        "jobs_new": len(new_urls),
        "jobs_updated": len(update_urls),
        "jobs_removed": len(stale_urls),
        "links_broken": broken,
    }
    return counters, details


def _rec_keys(rec: Any):
    """Keys of an asyncpg.Record or a plain dict (test fakes)."""
    return rec.keys()


def scrape_career_source(
    url: str, *, employer_name: str, max_jobs: int = 200,
    stats: Optional[dict[str, int]] = None,
) -> tuple[str, list[Any]]:
    """Platform-aware scrape with generic fallback. Sync (run in a thread).

    Returns (platform, jobs). platform is 'blocked' when the SSRF guard
    rejected the URL, 'generic' when the fallback path produced jobs, and
    'unknown' when nothing could be scraped.
    """
    platform, jobs = universal_scrape(url, employer_name=employer_name, max_jobs=max_jobs)
    if platform == "blocked":
        return "blocked", []
    if jobs:
        return platform, jobs
    generic = generic_careers_scrape(url, employer_name=employer_name, max_jobs=max_jobs,
                                     stats=stats)
    if generic:
        return "generic", generic
    return platform if platform != "unknown" else "unknown", []


def _parse_profile(val: Any) -> Optional[dict[str, Any]]:
    """extraction_profile arrives as dict (json codec) or str (raw JSONB)."""
    if not val:
        return None
    for _ in range(2):   # tolerate a double-encoded JSON string
        if isinstance(val, dict):
            return val
        try:
            val = json.loads(val)
        except (TypeError, json.JSONDecodeError):
            return None
    return val if isinstance(val, dict) else None


# Flap protection: a posting must be absent from this many CONSECUTIVE listing
# syncs before it is marked vanished (and its published job deactivated). One
# scrape hiccup — a half-rendered listing, a flaky CDN — can't unpublish live
# jobs. Reappearance resets the counter.
STALE_AFTER_MISSES = 2

# Adaptive cadence: after this many consecutive zero-change syncs, the
# effective auto-sync interval doubles (capped at max(24h, base)). Any
# observed change snaps the interval back to the employer-set base.
NO_CHANGE_RELAX_AFTER = 6


# Blast-radius guard: even a COMPLETE crawl does not get to mass-deactivate a
# source. A sync that would stale more than this share of a source's live
# postings stales nothing, parks the source in needs_attention, and files an
# admin review item. A real mass closure is rare and can be confirmed by a
# human in a minute; a scraper regression that silently empties the catalog
# cannot be undone by one.
BLAST_RADIUS_FRACTION = 0.30
BLAST_RADIUS_MIN = 25


def live_urls(stored: dict[str, dict[str, Any]]) -> set[str]:
    """Stored postings currently believed to be live on the site."""
    return {u for u, r in stored.items() if not r.get("vanished_at")}


def grace_urls(stored: dict[str, dict[str, Any]], present: set[str]) -> set[str]:
    """Stored live postings absent from this sync but still within the
    consecutive-miss grace window — they are NOT staled this sync."""
    out: set[str] = set()
    for url, row in stored.items():
        if url in present or row.get("vanished_at"):
            continue
        if int(row.get("consecutive_misses") or 0) + 1 < STALE_AFTER_MISSES:
            out.add(url)
    return out


def removal_candidates(stored: dict[str, dict[str, Any]], present: set[str]) -> set[str]:
    """Live stored postings this sync would actually stale (grace exhausted)."""
    return {
        u for u, r in stored.items()
        if u not in present and not r.get("vanished_at")
        and int(r.get("consecutive_misses") or 0) + 1 >= STALE_AFTER_MISSES
    }


def blast_radius_threshold(live_count: int) -> int:
    """Most postings one sync may remove: 30% of the live set, floor 25."""
    return max(BLAST_RADIUS_MIN, int(live_count * BLAST_RADIUS_FRACTION))


def exceeds_blast_radius(removal_count: int, live_count: int) -> bool:
    return removal_count > 0 and removal_count > blast_radius_threshold(live_count)


def plan_removals(
    stored: dict[str, dict[str, Any]], present: set[str], *, listing_complete: bool,
) -> tuple[str, set[str], int, int]:
    """Decide what this sync is allowed to remove.

    Returns (mode, protected_urls, would_remove, live_count) where mode is
    'applied' | 'skipped_incomplete' | 'held_for_review' and ``protected_urls``
    are treated as still-present for row staleness.

      applied            — complete crawl within the blast radius: only the
                           miss-grace window protects anything.
      skipped_incomplete — the crawl never saw the whole listing, so absence
                           proves nothing. Everything live is protected.
      held_for_review    — complete crawl, but the removal set is too large to
                           act on unattended. Everything live is protected and
                           an admin decides.
    """
    live = live_urls(stored)
    if not listing_complete:
        return "skipped_incomplete", live, 0, len(live)
    would_remove = len(removal_candidates(stored, present))
    if exceeds_blast_radius(would_remove, len(live)):
        return "held_for_review", live, would_remove, len(live)
    return "applied", grace_urls(stored, present), would_remove, len(live)


async def _load_fingerprints(conn, source_id: str) -> dict[str, dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT source_url, title, fingerprint, listing_fingerprint, vanished_at, "
        "consecutive_misses "
        "FROM public.career_source_jobs WHERE source_id = $1::uuid",
        source_id,
    )
    return {r["source_url"]: dict(r) for r in rows}


async def _store_fingerprints(
    conn, source_id: str, present: dict[str, Optional[str]],
    fetched_jobs: list[Any], stored: dict[str, dict[str, Any]],
    *, accrue_misses: bool = True,
) -> None:
    """Upsert per-URL fingerprint memory after a sync.

    ``accrue_misses`` gates the absence half. It is False whenever the crawl
    was not a complete census of the site (partial listing, cap hit) or the
    removal set was held for review: a posting we never looked for has not
    been missed, and counting it as one is how a first-page-only crawl
    silently unpublishes a catalog.
    """
    from app.skilled_pro.career_profile import scraped_job_fingerprint

    fetched_by_url = {j.source_url: j for j in fetched_jobs if j.source_url}
    for url, listing_fp in present.items():
        j = fetched_by_url.get(url)
        full_fp = scraped_job_fingerprint(j) if j is not None else None
        title = j.title if j is not None else None
        prev = stored.get(url)
        content_changed = j is not None and (
            prev is None or prev.get("fingerprint") != full_fp
        )
        await conn.execute(
            """
            INSERT INTO public.career_source_jobs
                (source_id, source_url, title, fingerprint, listing_fingerprint)
            VALUES ($1::uuid, $2, $3, $4, $5)
            ON CONFLICT (source_id, source_url) DO UPDATE SET
                title = COALESCE(EXCLUDED.title, public.career_source_jobs.title),
                fingerprint = COALESCE(EXCLUDED.fingerprint, public.career_source_jobs.fingerprint),
                listing_fingerprint = COALESCE(EXCLUDED.listing_fingerprint,
                                               public.career_source_jobs.listing_fingerprint),
                last_seen_at = now(),
                vanished_at = NULL,
                consecutive_misses = 0,
                last_changed_at = CASE WHEN $6 THEN now()
                                       ELSE public.career_source_jobs.last_changed_at END
            """,
            source_id, url, title, full_fp, listing_fp, content_changed,
        )
    if not accrue_misses:
        return
    # Absent postings accrue a miss; only STALE_AFTER_MISSES consecutive misses
    # actually vanish the row (flap protection — see grace_urls).
    await conn.execute(
        "UPDATE public.career_source_jobs SET "
        "consecutive_misses = consecutive_misses + 1, "
        "vanished_at = CASE WHEN consecutive_misses + 1 >= $3 THEN now() "
        "                   ELSE vanished_at END "
        "WHERE source_id = $1::uuid AND vanished_at IS NULL "
        "AND NOT (source_url = ANY($2::text[]))",
        source_id, list(present.keys()), STALE_AFTER_MISSES,
    )


def _removal_details(
    mode: str, *, listing_complete: bool, seen: int, pages: int,
    would_remove: int, live_count: int,
) -> dict[str, Any]:
    """The honest, human half of the removal decision for the sync timeline."""
    base: dict[str, Any] = {
        "removal_detection": mode,
        "listing_complete": bool(listing_complete),
        "listing_pages": pages,
    }
    if mode == "skipped_incomplete":
        base["listing_complete"] = False
        base["removal_note"] = (
            f"Checked the first {seen} listing{'' if seen == 1 else 's'} on this site. "
            "Removal detection stays off until a scan reaches the last page."
        )
    elif mode == "held_for_review":
        base["removal_hold"] = {"would_remove": would_remove, "live": live_count}
        base["removal_note"] = (
            f"This sync would have removed {would_remove} of {live_count} live jobs. "
            "Nothing was removed. An admin needs to confirm the removals first."
        )
    return base


async def _file_removal_hold(
    conn, source_id: str, employer_name: str, would_remove: int, live_count: int,
) -> None:
    """Park the source and queue one pending admin review item for it."""
    description = (
        f"{employer_name} careers sync would have removed {would_remove} of "
        f"{live_count} live jobs in one pass. Nothing was removed. Check the "
        "source site, then re-sync or remove the jobs by hand."
    )
    flags = {"would_remove": would_remove, "live": live_count,
             "guard": "removal_blast_radius"}
    await conn.execute(
        "UPDATE public.review_queue_items SET description = $2, flags = $3::jsonb, "
        "updated_at = now() WHERE entity_type = 'career_source' "
        "AND entity_id = $1::uuid AND status = 'pending'",
        source_id, description, flags,
    )
    await conn.execute(
        """
        INSERT INTO public.review_queue_items
            (item_type, entity_type, entity_id, description, flags, priority)
        SELECT 'suspicious_import', 'career_source', $1::uuid, $2, $3::jsonb, 2
         WHERE NOT EXISTS (
            SELECT 1 FROM public.review_queue_items
             WHERE entity_type = 'career_source' AND entity_id = $1::uuid
               AND status = 'pending')
        """,
        source_id, description, flags,
    )


async def run_pull(
    conn,
    source: dict[str, Any],
    *,
    triggered_by: Optional[str] = None,
    max_jobs: int = 200,
    force_full: bool = False,
) -> dict[str, Any]:
    """Execute one pull for a connected careers source.

    First pull (or ``force_full``): full discovery, then persist an extraction
    profile — the learned site structure. Every later pull reuses the profile
    for an INSTANT incremental sync: one conditional listing fetch (a 304
    short-circuits), detail fetches only for new/changed postings, vanished
    ones stale immediately, unchanged ones untouched. If the profile stops
    matching the site, the pull falls back to full discovery, rebuilds the
    profile, and records "structure changed — relearned" in the log.

    `source` needs: id, employer_id, url, batch_id (nullable), employer_name
    (+ auto_sync fields when present). Records a career_source_pulls history
    row (with sync_mode, duration, fetch count, and per-title details) and
    updates the source's last-pull + next-auto-sync state.
    """
    import asyncio

    t0 = time.monotonic()
    source_id = str(source["id"])
    url = source["url"]
    employer_name = source.get("employer_name") or "Unknown"

    counters = {"jobs_found": 0, "jobs_new": 0, "jobs_updated": 0,
                "jobs_removed": 0, "jobs_rejected": 0, "links_broken": 0}
    platform: str = "unknown"
    status = "ok"
    error: Optional[str] = None
    batch_id: Optional[str] = str(source["batch_id"]) if source.get("batch_id") else None
    sync_mode = "full"
    details: dict[str, Any] = {}
    fetch_count: Optional[int] = None
    profile = _parse_profile(source.get("extraction_profile"))
    new_profile: Optional[dict[str, Any]] = None
    listing_complete: Optional[bool] = None
    removal_detection = "not_applicable"
    held: Optional[dict[str, int]] = None

    try:
        from app.skilled_pro import career_profile as cp

        inc = None
        stored: dict[str, dict[str, Any]] = {}
        if profile is not None and not force_full:
            stored = await _load_fingerprints(conn, source_id)
            stats: dict[str, Any] = {}
            try:
                inc = await asyncio.to_thread(
                    cp.incremental_scrape, url, profile, stored,
                    employer_name=employer_name, max_jobs=max_jobs, stats=stats,
                )
                sync_mode = "incremental"
                fetch_count = int(stats.get("fetches", 0))
            except cp.ProfileStaleError as exc:
                logger.info("Profile stale for source %s (%s) — relearning", source_id, exc)
                sync_mode = "relearned"
                details["relearned"] = True
                details["note"] = "Site structure changed. Relearned the page layout."
                inc = None

        if inc is not None and inc.not_modified:
            # The site said 304 Not Modified — provably nothing changed.
            sync_mode = "not_modified"
            platform = profile.get("platform") or source.get("platform") or "unknown"
            live = sum(1 for r in stored.values() if not r.get("vanished_at"))
            counters["jobs_found"] = live
            details["unchanged"] = live
            new_profile = {**profile, "http": {**(profile.get("http") or {}), **inc.http}}
        elif inc is not None:
            platform = profile.get("platform") or "generic"
            counters["jobs_found"] = len(inc.present)
            scraped = [
                j for j in inc.jobs
                if j.source_url and j.source_url.rstrip("/") != url.rstrip("/")
            ]
            kept, rejected = filter_trades(scraped)
            counters["jobs_rejected"] = rejected + inc.early_rejected
            link_results = await asyncio.to_thread(
                check_apply_links, [j.source_url for j in kept]
            )
            batch_id = await _ensure_batch(conn, source, platform, triggered_by=triggered_by)
            # Removals are only meaningful against a COMPLETE census of the
            # site, and even then only within the blast radius. Everything
            # else is protected: absent-but-unproven, not removed.
            on_site = set(inc.present)
            listing_complete = inc.complete
            removal_detection, protected, would_remove, live_count = plan_removals(
                stored, on_site, listing_complete=inc.complete)
            sync_counts, sync_details = await sync_rows(
                conn, batch_id, kept, link_results, present_urls=on_site | protected,
            )
            counters.update(sync_counts)
            details.update(sync_details)
            await _store_fingerprints(
                conn, source_id, dict(inc.present), kept, stored,
                accrue_misses=removal_detection == "applied",
            )
            details.update(_removal_details(
                removal_detection, listing_complete=inc.complete,
                seen=len(inc.present), pages=inc.pages_crawled,
                would_remove=would_remove, live_count=live_count,
            ))
            if removal_detection == "held_for_review":
                held = {"would_remove": would_remove, "live": live_count}
            new_profile = {**profile, "http": {**(profile.get("http") or {}), **inc.http}}
        else:
            # Full discovery — first pull, forced refresh, or stale-profile relearn.
            scrape_stats: dict[str, Any] = {}
            platform, scraped = await asyncio.to_thread(
                scrape_career_source, url, employer_name=employer_name, max_jobs=max_jobs,
                stats=scrape_stats,
            )
            if platform == "blocked":
                status, error = "blocked", HUMAN_ERRORS["blocked"]
            elif not scraped:
                status, error = "no_jobs", HUMAN_ERRORS["no_jobs"]
            else:
                counters["jobs_found"] = len(scraped)
                # Drop anything without a canonical posting URL (apply links must
                # always work — the careers root is not an apply link).
                scraped = [
                    j for j in scraped
                    if j.source_url and j.source_url.rstrip("/") != url.rstrip("/")
                ]
                kept, rejected = filter_trades(scraped)
                early = scrape_stats.get("early_rejected", 0)
                counters["jobs_found"] += early  # anchors seen but skipped pre-fetch
                counters["jobs_rejected"] = rejected + early
                link_results = await asyncio.to_thread(
                    check_apply_links, [j.source_url for j in kept]
                )
                batch_id = await _ensure_batch(conn, source, platform, triggered_by=triggered_by)
                # Same removal rules as the incremental path: a full pull that
                # only reached page one is just as blind.
                fp_stored = await _load_fingerprints(conn, source_id)
                on_site = {j.source_url for j in scraped if j.source_url}
                listing_complete = bool(scrape_stats.get("listing_complete")) \
                    if "listing_complete" in scrape_stats else platform != "generic"
                removal_detection, protected, would_remove, live_count = plan_removals(
                    fp_stored, on_site, listing_complete=listing_complete)
                sync_counts, sync_details = await sync_rows(
                    conn, batch_id, kept, link_results, present_urls=on_site | protected,
                )
                counters.update(sync_counts)
                details.update(sync_details)
                details.update(_removal_details(
                    removal_detection, listing_complete=listing_complete,
                    seen=len(on_site), pages=int(scrape_stats.get("listing_pages") or 1),
                    would_remove=would_remove, live_count=live_count,
                ))
                if removal_detection == "held_for_review":
                    held = {"would_remove": would_remove, "live": live_count}

                # Learn (or relearn) the site structure for instant re-syncs.
                sitemap = None
                if platform == "generic" and scrape_stats.get("fetches"):
                    # (Guarded on real fetches having happened so fully-mocked
                    # test runs never touch the network.)
                    sitemap = await asyncio.to_thread(cp.probe_sitemap, url, stats=scrape_stats)
                http_meta = {
                    "etag": scrape_stats.get("listing_etag"),
                    "last_modified": scrape_stats.get("listing_last_modified"),
                    "supports_304": None,
                }
                new_profile = cp.build_extraction_profile(
                    platform=platform, url=url,
                    job_urls=[j.source_url for j in scraped if j.source_url],
                    jsonld_listing=bool(scrape_stats.get("jsonld_listing")),
                    sitemap_available=sitemap,
                    http_meta=http_meta,
                )
                await _store_fingerprints(
                    conn, source_id,
                    {j.source_url: None for j in scraped if j.source_url},
                    scraped, fp_stored,
                    accrue_misses=removal_detection == "applied",
                )
                # Platform adapters fetch listing pages + one detail per job;
                # the generic path counts exactly. Report the honest number.
                fetch_count = int(scrape_stats.get("fetches") or 0) or (
                    len(scraped) + 1 if platform != "generic" else None
                )
    except Exception as exc:  # noqa: BLE001 — a pull must always record its outcome
        # Raw exception text goes to the log only — the stored/returned error
        # is always a human sentence (the timeline renders it verbatim).
        logger.exception("Career-source pull failed for %s: %s", source_id, exc)
        status, error = "error", HUMAN_ERRORS["error"]

    duration_ms = int((time.monotonic() - t0) * 1000)

    # ---- Adaptive cadence -------------------------------------------------
    # The employer-set interval is the BASE (and floor). When the last
    # NO_CHANGE_RELAX_AFTER successful syncs all found zero changes, the
    # effective interval relaxes (×2, capped at max(24h, base)); the moment a
    # sync observes any change it snaps back to the base. Failures keep the
    # existing exponential backoff off the base. Adaptations are logged into
    # the pull's details so the sync timeline explains the cadence honestly.
    base_h = int(source.get("auto_sync_interval_hours") or 6)
    adaptive_h = max(int(source.get("adaptive_interval_hours") or base_h), base_h)
    streak = int(source.get("no_change_streak") or 0)
    if status == "ok":
        failures = 0
        changed = (counters["jobs_new"] + counters["jobs_updated"]
                   + counters["jobs_removed"]) > 0
        if changed:
            if adaptive_h != base_h:
                details["cadence"] = (
                    f"Auto-sync tightened back to every {base_h}h: changes detected."
                )
            streak, adaptive_h = 0, base_h
        else:
            streak += 1
            if streak >= NO_CHANGE_RELAX_AFTER:
                relaxed = min(adaptive_h * 2, max(24, base_h))
                if relaxed != adaptive_h:
                    span_h = streak * adaptive_h
                    span = (f"{span_h // 24} day{'s' if span_h // 24 != 1 else ''}"
                            if span_h >= 24 else f"{span_h} hours")
                    details["cadence"] = (
                        f"Auto-sync relaxed to every {relaxed}h: "
                        f"no changes in {span}."
                    )
                    adaptive_h = relaxed
                streak = 0
        delay_h = adaptive_h
    else:
        failures = int(source.get("consecutive_failures") or 0) + 1
        delay_h = base_h * min(2 ** max(0, failures - 1), 8)

    pull_id = await conn.fetchval(
        """
        INSERT INTO public.career_source_pulls
            (source_id, batch_id, triggered_by, status, platform, error,
             jobs_found, jobs_new, jobs_updated, jobs_removed, jobs_rejected, links_broken,
             sync_mode, duration_ms, fetch_count, details,
             listing_complete, removal_detection)
        VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                $13, $14, $15, $16::jsonb, $17, $18)
        RETURNING id::text
        """,
        source_id, batch_id, triggered_by, status, platform, error,
        counters["jobs_found"], counters["jobs_new"], counters["jobs_updated"],
        counters["jobs_removed"], counters["jobs_rejected"], counters["links_broken"],
        # The pooled-connection JSONB codec json-dumps Python values itself —
        # pass the dict, never a pre-dumped string (that double-encodes).
        sync_mode, duration_ms, fetch_count, details,
        listing_complete, removal_detection,
    )

    # True = park the source, False = a clean complete sync clears the park,
    # None = this pull proves nothing either way, so leave the flag alone.
    attention_state: Optional[bool] = (
        True if held is not None
        else False if removal_detection == "applied"
        else None
    )
    if held is not None:
        await _file_removal_hold(conn, source_id, employer_name,
                                 held["would_remove"], held["live"])

    # A source that has NEVER produced a job stays in the "couldn't connect"
    # holding state: auto-sync off, nothing scheduled. The first pull that
    # finds ≥1 job flips auto-sync on; after that the employer's own setting
    # is respected (None = leave as-is).
    succeeded_now = status == "ok" and counters["jobs_found"] > 0
    succeeded_before = (
        source.get("last_status") == "ok" and int(source.get("jobs_found") or 0) > 0
    )
    if succeeded_now and not succeeded_before:
        auto_sync_override: Optional[bool] = True
    elif not succeeded_now and not succeeded_before:
        auto_sync_override = False
    else:
        auto_sync_override = None

    await conn.execute(
        """
        UPDATE public.employer_career_sources SET
            platform = COALESCE($2, platform), batch_id = COALESCE($3::uuid, batch_id),
            last_pulled_at = now(), last_status = $4, last_error = $5,
            jobs_found = $6,
            extraction_profile = COALESCE($7::jsonb, extraction_profile),
            consecutive_failures = $8,
            auto_sync_enabled = COALESCE($10, auto_sync_enabled),
            next_auto_sync_at = CASE
                WHEN COALESCE($10, auto_sync_enabled) THEN now() + make_interval(hours => $9)
                ELSE NULL
            END,
            no_change_streak = $11,
            adaptive_interval_hours = $12,
            -- Parked for a human by the blast-radius guard. Only a sync that
            -- completed AND applied its removals clears the flag; a failed or
            -- partial sync leaves an existing hold standing (NULL = leave).
            needs_attention = COALESCE($13, needs_attention),
            attention_reason = CASE WHEN $13 IS NULL THEN attention_reason
                                    WHEN $13 THEN $14 ELSE NULL END,
            attention_at = CASE WHEN $13 IS NULL THEN attention_at
                                WHEN $13 THEN now() ELSE NULL END,
            updated_at = now()
        WHERE id = $1::uuid
        """,
        source_id, platform if platform not in ("unknown", "blocked") else None,
        batch_id, status, error, counters["jobs_found"],
        new_profile,   # dict — the pooled JSONB codec handles encoding
        failures, delay_h, auto_sync_override,
        streak, adaptive_h if adaptive_h != base_h else None,
        attention_state, details.get("removal_note"),
    )
    return {"pull_id": pull_id, "batch_id": batch_id, "status": status,
            "platform": platform, "error": error,
            "sync_mode": sync_mode, "duration_ms": duration_ms,
            "fetch_count": fetch_count, "details": details,
            "listing_complete": listing_complete,
            "removal_detection": removal_detection, **counters}


# ============================================================================
# Headless fallback pull (scheduler-only — see app/skilled_pro/headless.py)
# ============================================================================

HEADLESS_INTERVAL_HOURS = 24    # headless renders are expensive: daily, always


def profile_is_headless(profile: Any) -> bool:
    p = _parse_profile(profile)
    return bool(p and p.get("headless"))


async def run_headless_pull(
    conn, source: dict[str, Any], *,
    triggered_by: Optional[str] = None, max_jobs: int = 200,
) -> dict[str, Any]:
    """One LISTING-ONLY headless pull for a JS-walled source.

    Renders the listing page in headless Chromium (background thread), then
    reuses the exact full-pull pipeline: trades filter → apply-link checks →
    dedupe-sync into the rolling batch → fingerprint memory (with the same
    consecutive-miss flap protection). Success marks the source's profile
    ``{"headless": true}`` so the auto-sync tick keeps routing it here on a
    DAILY cadence; finding nothing keeps the honest no_jobs state.
    """
    import asyncio

    from app.config import get_settings

    t0 = time.monotonic()
    source_id = str(source["id"])
    url = source["url"]
    employer_name = source.get("employer_name") or "Unknown"
    counters = {"jobs_found": 0, "jobs_new": 0, "jobs_updated": 0,
                "jobs_removed": 0, "jobs_rejected": 0, "links_broken": 0}
    status = "ok"
    error: Optional[str] = None
    batch_id: Optional[str] = str(source["batch_id"]) if source.get("batch_id") else None
    details: dict[str, Any] = {"headless": True}
    fetch_count: Optional[int] = None
    new_profile: Optional[dict[str, Any]] = None
    listing_complete: Optional[bool] = None
    removal_detection = "not_applicable"
    held: Optional[dict[str, int]] = None

    try:
        if not get_settings().headless_scrape_enabled:
            raise BlockedURLError("headless scraping disabled")
        validate_public_url(url)
        from app.skilled_pro.headless import headless_careers_scrape

        scrape_stats: dict[str, Any] = {}
        scraped = await asyncio.to_thread(
            headless_careers_scrape, url, employer_name=employer_name,
            max_jobs=max_jobs, stats=scrape_stats,
        )
        fetch_count = int(scrape_stats.get("fetches") or 0) + 1  # +1 = the render
        if not scraped:
            status, error = "no_jobs", HUMAN_ERRORS["no_jobs"]
        else:
            counters["jobs_found"] = len(scraped) + int(scrape_stats.get("early_rejected") or 0)
            scraped = [j for j in scraped
                       if j.source_url and j.source_url.rstrip("/") != url.rstrip("/")]
            kept, rejected = filter_trades(scraped)
            counters["jobs_rejected"] = rejected + int(scrape_stats.get("early_rejected") or 0)
            link_results = await asyncio.to_thread(
                check_apply_links, [j.source_url for j in kept]
            )
            batch_id = await _ensure_batch(conn, source, "headless",
                                           triggered_by=triggered_by)
            fp_stored = await _load_fingerprints(conn, source_id)
            on_site = {j.source_url for j in scraped if j.source_url}
            listing_complete = bool(scrape_stats.get("listing_complete"))
            removal_detection, protected, would_remove, live_count = plan_removals(
                fp_stored, on_site, listing_complete=listing_complete)
            sync_counts, sync_details = await sync_rows(
                conn, batch_id, kept, link_results, present_urls=on_site | protected,
            )
            counters.update(sync_counts)
            details.update(sync_details)
            await _store_fingerprints(
                conn, source_id,
                {j.source_url: None for j in scraped if j.source_url},
                scraped, fp_stored,
                accrue_misses=removal_detection == "applied",
            )
            details.update(_removal_details(
                removal_detection, listing_complete=listing_complete,
                seen=len(on_site), pages=int(scrape_stats.get("listing_pages") or 1),
                would_remove=would_remove, live_count=live_count,
            ))
            if removal_detection == "held_for_review":
                held = {"would_remove": would_remove, "live": live_count}
            prev = _parse_profile(source.get("extraction_profile")) or {}
            new_profile = {
                **prev,
                "profile_version": prev.get("profile_version", 1),
                "platform": "headless",
                "listing_url": url,
                "headless": True,
            }
            details["note"] = (
                "This site renders its jobs with JavaScript, so it syncs via the "
                "daily headless browser pass."
            )
    except BlockedURLError:
        status, error = "blocked", HUMAN_ERRORS["blocked"]
    except Exception as exc:  # noqa: BLE001 — a pull must always record its outcome
        logger.exception("Headless pull failed for %s: %s", source_id, exc)
        status, error = "error", HUMAN_ERRORS["error"]

    duration_ms = int((time.monotonic() - t0) * 1000)
    pull_id = await conn.fetchval(
        """
        INSERT INTO public.career_source_pulls
            (source_id, batch_id, triggered_by, status, platform, error,
             jobs_found, jobs_new, jobs_updated, jobs_removed, jobs_rejected, links_broken,
             sync_mode, duration_ms, fetch_count, details,
             listing_complete, removal_detection)
        VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                'headless', $13, $14, $15::jsonb, $16, $17)
        RETURNING id::text
        """,
        source_id, batch_id, triggered_by, status, "headless", error,
        counters["jobs_found"], counters["jobs_new"], counters["jobs_updated"],
        counters["jobs_removed"], counters["jobs_rejected"], counters["links_broken"],
        duration_ms, fetch_count, details, listing_complete, removal_detection,
    )

    attention_state: Optional[bool] = (
        True if held is not None
        else False if removal_detection == "applied"
        else None
    )
    if held is not None:
        await _file_removal_hold(conn, source_id, employer_name,
                                 held["would_remove"], held["live"])

    succeeded = status == "ok" and counters["jobs_found"] > 0
    failures = 0 if status == "ok" else int(source.get("consecutive_failures") or 0) + 1
    await conn.execute(
        """
        UPDATE public.employer_career_sources SET
            platform = COALESCE($2, platform), batch_id = COALESCE($3::uuid, batch_id),
            last_pulled_at = now(), last_status = $4, last_error = $5,
            jobs_found = $6,
            extraction_profile = COALESCE($7::jsonb, extraction_profile),
            consecutive_failures = $8,
            auto_sync_enabled = CASE WHEN $9 THEN TRUE ELSE auto_sync_enabled END,
            next_auto_sync_at = CASE
                WHEN $9 OR auto_sync_enabled
                    THEN now() + make_interval(hours => $10)
                ELSE NULL
            END,
            needs_attention = COALESCE($11, needs_attention),
            attention_reason = CASE WHEN $11 IS NULL THEN attention_reason
                                    WHEN $11 THEN $12 ELSE NULL END,
            attention_at = CASE WHEN $11 IS NULL THEN attention_at
                                WHEN $11 THEN now() ELSE NULL END,
            updated_at = now()
        WHERE id = $1::uuid
        """,
        source_id, "headless" if succeeded else None, batch_id, status, error,
        counters["jobs_found"], new_profile, failures, succeeded,
        HEADLESS_INTERVAL_HOURS, attention_state, details.get("removal_note"),
    )
    return {"pull_id": pull_id, "batch_id": batch_id, "status": status,
            "platform": "headless", "error": error, "sync_mode": "headless",
            "duration_ms": duration_ms, "fetch_count": fetch_count,
            "details": details, "listing_complete": listing_complete,
            "removal_detection": removal_detection, **counters}


async def _ensure_batch(
    conn, source: dict[str, Any], platform: str, *, triggered_by: Optional[str] = None,
) -> str:
    """Return the source's rolling batch id, creating the batch if missing."""
    if source.get("batch_id"):
        exists = await conn.fetchval(
            "SELECT 1 FROM public.job_import_batches WHERE id = $1::uuid",
            str(source["batch_id"]),
        )
        if exists:
            return str(source["batch_id"])
    created_by = str(source.get("created_by") or triggered_by or "")
    row = await conn.fetchrow(
        """
        INSERT INTO public.job_import_batches
            (employer_id, created_by, source, source_label, platform, status)
        VALUES ($1::uuid, $2::uuid, 'url', $3, $4, 'draft')
        RETURNING id::text AS id
        """,
        str(source["employer_id"]), created_by, source["url"],
        platform if platform not in ("unknown", "blocked") else None,
    )
    await conn.execute(
        "UPDATE public.employer_career_sources SET batch_id = $2::uuid, updated_at = now() "
        "WHERE id = $1::uuid",
        str(source["id"]), row["id"],
    )
    source["batch_id"] = row["id"]
    return row["id"]


# ---------------------------------------------------------------------------
# Fast-lane freshness: cheap listing fingerprints between full syncs
# ---------------------------------------------------------------------------
# "No stale jobs" without an API key: every scheduler tick (15 min), each
# connected source gets ONE cheap probe — the listing page (or the platform's
# page-1 search JSON) — hashed down to the set of posting identifiers. A
# changed fingerprint triggers a real incremental pull immediately; an
# unchanged one costs a single HTTP request. Detection latency therefore
# tracks the tick interval (~15 min) instead of the 6h-and-adaptive cadence,
# while total load stays at one request per source per tick.

def compute_listing_fingerprint(url: str, platform: str | None) -> Optional[str]:
    """One-fetch content fingerprint of a source's CURRENT posting set.

    Returns a stable hash of the posting identifiers visible on the first
    listing page, or None when the probe fails (callers treat None as
    "unknown — do nothing"; a probe failure must never trigger a pull storm).
    Sync — run in a thread.
    """
    import hashlib

    from app.util.net_guard import BlockedURLError, safe_get_sync, validate_public_url

    try:
        validate_public_url(url)
    except BlockedURLError:
        return None

    ids: list[str] = []
    try:
        if platform == "cornerstone":
            import httpx as _httpx
            from scraper.universal import _CSOD_TOKEN_RE, _parse_cornerstone  # type: ignore
            parsed = _parse_cornerstone(url)
            if not parsed:
                return None
            host, site_id, corp = parsed
            with _httpx.Client(headers={"User-Agent": "Mozilla/5.0"}, timeout=15.0,
                               follow_redirects=True) as client:
                home = client.get(f"https://{host}/ux/ats/careersite/{site_id}/home",
                                  params={"c": corp})
                tok = _CSOD_TOKEN_RE.search(home.text or "")
                if home.status_code != 200 or not tok:
                    return None
                r = client.post(
                    f"https://{host}/services/x/career-site/v1/search",
                    headers={"Authorization": f"Bearer {tok.group(1)}",
                             "Content-Type": "application/json"},
                    json={"careerSiteId": site_id, "careerSitePageId": site_id,
                          "pageNumber": 1, "pageSize": 100, "cultureId": 1,
                          "cultureName": "en-US", "searchText": "", "states": [],
                          "countryCodes": [], "cities": [], "placeID": "",
                          "radius": None, "postingsWithinDays": None,
                          "customFieldCheckboxKeys": [], "customFieldDropdowns": [],
                          "customFieldRadios": []})
                if r.status_code != 200:
                    return None
                reqs = ((r.json() or {}).get("data") or {}).get("requisitions") or []
                ids = [f"{q.get('requisitionId')}:{q.get('postingEffectiveDate')}"
                       for q in reqs]
        else:
            # Generic + every HTML-shell platform: one GET of the listing URL,
            # fingerprint the discovered job links.
            r = safe_get_sync(url, timeout=15.0, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return None
            ids = [u for u, _t in discover_job_links(r.text, url)]
    except Exception:
        return None
    if not ids:
        return None
    return hashlib.sha256("\n".join(sorted(set(ids))).encode()).hexdigest()[:32]


async def fast_freshness_check(conn, source: dict[str, Any]) -> bool:
    """Probe one source; pull immediately if its posting set changed.

    Returns True when a pull was triggered. Stores the fingerprint in
    extraction_profile.listing_hash either way, so the next tick compares
    against current reality.
    """
    import asyncio as _aio

    profile = _parse_profile(source.get("extraction_profile")) or {}
    fp = await _aio.to_thread(
        compute_listing_fingerprint, source["url"], source.get("platform"))
    if fp is None:
        return False
    prev = profile.get("listing_hash")
    if prev == fp:
        return False
    changed = prev is not None       # first-ever probe just seeds the hash
    profile["listing_hash"] = fp
    await conn.execute(
        """UPDATE public.employer_career_sources
              SET extraction_profile = COALESCE(extraction_profile, '{}'::jsonb)
                  || jsonb_build_object('listing_hash', $2::text),
                  updated_at = now()
            WHERE id = $1""",
        source["id"], fp,
    )
    if changed:
        await run_pull(conn, source, triggered_by=None)
        return True
    return False
