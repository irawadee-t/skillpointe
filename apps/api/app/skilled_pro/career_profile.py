"""
career_profile.py — Learned site structure + instant incremental re-sync.

The first pull of a careers source is slow on purpose: it discovers how the
site is laid out. Everything it learns is persisted on
``employer_career_sources.extraction_profile`` (JSONB) so every later sync can
skip discovery entirely:

  • platform + API params (Workday tenant/site, Greenhouse board, Lever site)
  • the listing URL + job-link URL patterns learned from successful anchors
  • whether JSON-LD JobPosting was present on the listing page
  • sitemap.xml availability (generic sites, informational)
  • HTTP cache validators (ETag / Last-Modified) and whether the server
    honours them with a 304 (measured, not assumed)

An incremental sync then costs:
  1 listing fetch  — conditional (If-None-Match / If-Modified-Since); a 304
                     short-circuits to "no changes" in well under a second
  + N detail fetches — ONLY for postings that are new or whose listing-level
                     fingerprint changed (parallel, capped)
  + 0 fetches       — for every unchanged posting

If a profile-driven sync finds nothing where jobs used to be (site redesigned),
``ProfileStaleError`` bubbles up and the caller falls back to full discovery,
rebuilds the profile, and records "structure changed — relearned" in the log.

Pure helpers up top (unit-tested offline); network functions go through the
SSRF guard and count every fetch into a caller-supplied ``stats`` dict.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

# Triggers the packages/ sys.path bootstrap as a side effect.
from app.skilled_pro.job_imports import universal_scrape  # noqa: F401
from app.util.net_guard import BlockedURLError, validate_public_url

logger = logging.getLogger(__name__)

PROFILE_VERSION = 1

_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_DETAIL_WORKERS = 6           # parallel detail fetches on incremental syncs
_MAX_LINK_PATTERNS = 5


class ProfileStaleError(Exception):
    """The learned profile no longer matches the site — relearn from scratch."""


# ============================================================================
# Fingerprints (pure)
# ============================================================================

_FP_FIELDS = (
    "title", "description", "responsibilities", "requirements", "qualifications",
    "city", "state", "pay_raw", "employment_type", "experience_level",
    "posted_date", "req_id", "work_setting",
)


def scraped_job_fingerprint(job: Any) -> str:
    """Stable content hash of every extracted field of a ScrapedJob."""
    payload = {f: getattr(job, f, None) for f in _FP_FIELDS}
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def text_fingerprint(*parts: Optional[str]) -> str:
    """Cheap listing-level hash (anchor text, API summary fields)."""
    norm = "|".join(re.sub(r"\s+", " ", (p or "")).strip().lower() for p in parts)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _titles_equal(a: Optional[str], b: Optional[str]) -> bool:
    na = re.sub(r"\s+", " ", (a or "")).strip().lower()
    nb = re.sub(r"\s+", " ", (b or "")).strip().lower()
    return bool(na) and na == nb


# ============================================================================
# URL-pattern learning (pure)
# ============================================================================

def learn_url_patterns(urls: list[str], *, max_patterns: int = _MAX_LINK_PATTERNS) -> list[str]:
    """Learn job-link URL regexes from the anchors that actually yielded jobs.

    Two passes, most-specific first:
      1. Group by (host, path-minus-last-segment): only the final segment
         varies (slug or req id). Groups with 2+ members become patterns.
      2. URLs left as singletons (every posting has its own slug, e.g.
         "/job/<City-Title-ST-ZIP>/<id>/") regroup by (host, first segment,
         path depth) with every following segment variable — one generalized
         pattern per shape instead of one dead pattern per posting.
    """
    parsed: list[tuple[str, list[str]]] = []
    for u in urls:
        try:
            p = urlparse(u)
        except ValueError:
            continue
        host = (p.hostname or "").lower()
        segs = [s for s in p.path.split("/") if s]
        if host and segs:
            parsed.append((host, segs))

    prefix_groups: dict[tuple[str, str], int] = {}
    for host, segs in parsed:
        key = (host, "/".join(segs[:-1]))
        prefix_groups[key] = prefix_groups.get(key, 0) + 1

    out: list[str] = []
    for (host, prefix), count in sorted(prefix_groups.items(), key=lambda kv: -kv[1]):
        if count < 2:
            continue
        base = re.escape(host) + ("/" + re.escape(prefix) if prefix else "")
        out.append(rf"^https?://{base}/[^/?#]+/?(?:[?#].*)?$")
        if len(out) >= max_patterns:
            return out

    shape_groups: dict[tuple[str, str, int], int] = {}
    for host, segs in parsed:
        if prefix_groups.get((host, "/".join(segs[:-1]))) >= 2:
            continue  # already covered by a specific pattern
        shape_groups[(host, segs[0], len(segs))] = \
            shape_groups.get((host, segs[0], len(segs)), 0) + 1
    for (host, first, depth), _count in sorted(shape_groups.items(), key=lambda kv: -kv[1]):
        tail = "/[^/?#]+" * (depth - 1)
        out.append(rf"^https?://{re.escape(host)}/{re.escape(first)}{tail}/?(?:[?#].*)?$")
        if len(out) >= max_patterns:
            break
    return out


def url_matches_patterns(url: str, patterns: list[str]) -> bool:
    for pat in patterns:
        try:
            if re.match(pat, url):
                return True
        except re.error:
            continue
    return False


# ============================================================================
# Profile build (pure given inputs)
# ============================================================================

def platform_params_from_url(platform: str, url: str) -> dict[str, Any]:
    """Extract the platform API params the incremental path needs."""
    if platform == "workday":
        from scraper.universal import _parse_workday  # type: ignore
        parsed = _parse_workday(url)
        if parsed:
            tenant, wd, site = parsed
            return {"tenant": tenant, "wd": wd, "site": site}
    elif platform == "greenhouse":
        from scraper.universal import _GH_BOARD_RE  # type: ignore
        m = _GH_BOARD_RE.search(url)
        if m:
            return {"board": m.group("board")}
    elif platform == "lever":
        from scraper.universal import _LEVER_SITE_RE  # type: ignore
        m = _LEVER_SITE_RE.search(url)
        if m:
            return {"site": m.group("site")}
    return {}


def build_extraction_profile(
    *,
    platform: str,
    url: str,
    job_urls: list[str],
    jsonld_listing: bool = False,
    sitemap_available: Optional[bool] = None,
    http_meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble the persisted profile after a successful full pull."""
    from datetime import datetime, timezone

    return {
        "profile_version": PROFILE_VERSION,
        "learned_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform,
        "platform_params": platform_params_from_url(platform, url),
        "listing_url": url,
        "link_patterns": learn_url_patterns(job_urls) if platform == "generic" else [],
        "jsonld_listing": jsonld_listing,
        "sitemap_available": sitemap_available,
        "http": dict(http_meta or {}),   # {etag, last_modified, supports_304}
    }


# ============================================================================
# Guarded HTTP helpers (every fetch counted into stats["fetches"])
# ============================================================================

def _count(stats: Optional[dict[str, int]]) -> None:
    if stats is not None:
        stats["fetches"] = stats.get("fetches", 0) + 1


def _guarded_get(
    url: str,
    *,
    stats: Optional[dict[str, int]],
    extra_headers: Optional[dict[str, str]] = None,
    max_redirects: int = 4,
) -> httpx.Response:
    """SSRF-safe GET with per-hop validation, counting each request."""
    headers = {"User-Agent": _UA, **(extra_headers or {})}
    current = url
    with httpx.Client(follow_redirects=False, timeout=_TIMEOUT, headers=headers) as client:
        for _ in range(max_redirects + 1):
            validate_public_url(current)
            _count(stats)
            resp = client.get(current)
            if resp.is_redirect and resp.headers.get("location"):
                current = str(resp.next_request.url) if resp.next_request else resp.headers["location"]
                continue
            return resp
    raise BlockedURLError("too many redirects")


def conditional_get(
    url: str,
    http_meta: dict[str, Any],
    *,
    stats: Optional[dict[str, int]] = None,
) -> tuple[Optional[httpx.Response], dict[str, Any]]:
    """GET with If-None-Match / If-Modified-Since from the stored validators.

    Returns (response | None, new_http_meta). ``None`` means the server said
    304 Not Modified — nothing changed, zero parsing needed. supports_304 is
    MEASURED: set True the first time a 304 actually comes back.
    """
    cond: dict[str, str] = {}
    if http_meta.get("etag"):
        cond["If-None-Match"] = http_meta["etag"]
    if http_meta.get("last_modified"):
        cond["If-Modified-Since"] = http_meta["last_modified"]
    resp = _guarded_get(url, stats=stats, extra_headers=cond)
    if resp.status_code == 304:
        return None, {**http_meta, "supports_304": True}
    new_meta = {
        "etag": resp.headers.get("etag") or http_meta.get("etag"),
        "last_modified": resp.headers.get("last-modified") or http_meta.get("last_modified"),
        "supports_304": http_meta.get("supports_304"),
    }
    return resp, new_meta


def probe_sitemap(url: str, *, stats: Optional[dict[str, int]] = None) -> Optional[bool]:
    """Best-effort: does the site expose a sitemap.xml? (Informational.)"""
    try:
        p = urlparse(url)
        target = f"{p.scheme}://{p.netloc}/sitemap.xml"
        validate_public_url(target)
        _count(stats)
        with httpx.Client(follow_redirects=False, timeout=httpx.Timeout(10.0, connect=5.0),
                          headers={"User-Agent": _UA}) as client:
            resp = client.head(target)
        return resp.status_code < 400
    except Exception:
        return None


# ============================================================================
# Incremental sync
# ============================================================================

@dataclass
class IncrementalResult:
    """What an incremental listing pass found.

    present:        every job URL currently on the site → listing fingerprint
    jobs:           full ScrapedJobs fetched for NEW or CHANGED postings only
    early_rejected: anchors skipped pre-fetch (clearly non-trades titles)
    http:           refreshed cache validators to persist back on the profile
    not_modified:   the listing 304'd — nothing changed anywhere
    complete:       the crawl reached the END of the listing (all pages walked
                    / full platform result set) with no cap or bound hit.
                    ``present`` is only a complete census of the site when this
                    is True; the caller must not run removal detection
                    otherwise. Defaults to False — completeness is proven, not
                    assumed.
    pages_crawled:  listing pages actually read
    """
    not_modified: bool = False
    present: dict[str, str] = field(default_factory=dict)
    jobs: list[Any] = field(default_factory=list)
    early_rejected: int = 0
    http: dict[str, Any] = field(default_factory=dict)
    complete: bool = False
    incomplete_reason: Optional[str] = None
    pages_crawled: int = 1


def _needs_detail(url: str, listing_fp: str, anchor_title: Optional[str],
                  stored: dict[str, dict[str, Any]]) -> bool:
    """Does this posting need a detail fetch? New, reappeared, or changed."""
    row = stored.get(url)
    if row is None or row.get("vanished_at"):
        return True
    prev_fp = row.get("listing_fingerprint")
    if prev_fp:
        return prev_fp != listing_fp
    # Profile learned by a full pull that had no listing-level fingerprints:
    # adopt the new fingerprint when the title still matches; refetch otherwise.
    return not _titles_equal(anchor_title, row.get("title"))


def incremental_scrape(
    url: str,
    profile: dict[str, Any],
    stored: dict[str, dict[str, Any]],
    *,
    employer_name: str,
    max_jobs: int = 200,
    stats: Optional[dict[str, int]] = None,
) -> IncrementalResult:
    """Profile-driven sync: NO discovery, listing + changed details only.

    ``stored`` maps source_url → {title, fingerprint, listing_fingerprint,
    vanished_at} from career_source_jobs. Raises ProfileStaleError when the
    profile no longer produces jobs (site changed) so the caller can relearn.
    """
    platform = profile.get("platform") or "generic"
    params = profile.get("platform_params") or {}
    http_meta = dict(profile.get("http") or {})
    listing_url = profile.get("listing_url") or url

    try:
        # Sitemap-first: when the source publishes a sitemap (discovered by
        # the freshness fast lane), ONE fetch replaces the entire listing
        # crawl AND is a complete census — the exact changed-posting set
        # falls out of the lastmod diff. Any failure falls through to the
        # platform/generic paths below.
        if profile.get("sitemap_url"):
            try:
                return _sitemap_incremental(
                    profile["sitemap_url"], url, stored,
                    employer_name=employer_name, max_jobs=max_jobs,
                    stats=stats, http_meta=http_meta)
            except (BlockedURLError, httpx.HTTPError, ProfileStaleError):
                pass
        if platform == "workday":
            return _workday_incremental(params, stored, employer_name=employer_name,
                                        max_jobs=max_jobs, stats=stats, http_meta=http_meta)
        if platform == "greenhouse":
            return _api_platform_incremental(
                "greenhouse", params, listing_url, stored, employer_name=employer_name,
                max_jobs=max_jobs, stats=stats, http_meta=http_meta)
        if platform == "lever":
            return _api_platform_incremental(
                "lever", params, listing_url, stored, employer_name=employer_name,
                max_jobs=max_jobs, stats=stats, http_meta=http_meta)
        return _generic_incremental(listing_url, profile, stored, employer_name=employer_name,
                                    max_jobs=max_jobs, stats=stats, http_meta=http_meta)
    except ProfileStaleError:
        raise
    except (BlockedURLError, httpx.HTTPError) as exc:
        raise ProfileStaleError(f"listing fetch failed: {exc}") from exc


def _sitemap_incremental(
    sitemap_url: str, source_url: str, stored: dict[str, dict[str, Any]], *,
    employer_name: str, max_jobs: int, stats: Optional[dict[str, int]],
    http_meta: dict[str, Any],
) -> IncrementalResult:
    """Sitemap-driven sync: the site's own change feed names exactly WHAT
    changed. present = every job URL in the sitemap (a complete census, so
    removal detection is legitimate); details are fetched ONLY for URLs that
    are new or whose <lastmod> moved. Cost: 1 sitemap fetch + K detail
    fetches, where K = number of actually-changed postings."""
    import time as _time
    from urllib.parse import urlparse as _urlparse

    from app.skilled_pro.career_sources import (
        _SITEMAP_LASTMOD_RE,
        _job_like,
        scrape_detail_page,
    )

    host = _urlparse(source_url).hostname or ""
    resp, new_meta = conditional_get(sitemap_url, http_meta, stats=stats)
    if resp is None:
        return IncrementalResult(not_modified=True, http=new_meta, complete=True)
    if resp.status_code >= 400:
        raise ProfileStaleError(f"sitemap returned {resp.status_code}")

    present: dict[str, str] = {}
    for u, lastmod in _SITEMAP_LASTMOD_RE.findall(resp.text):
        if _job_like(u, host):
            present[u] = lastmod or ""
    if not present:
        raise ProfileStaleError("sitemap no longer lists job URLs")

    to_fetch: list[str] = []
    for u, lastmod in present.items():
        rec = stored.get(u)
        if rec is None or rec.get("vanished_at"):
            to_fetch.append(u)                      # new (or resurrected)
        elif lastmod and rec.get("listing_fingerprint") not in ("", None, lastmod):
            to_fetch.append(u)                      # lastmod moved -> changed
    to_fetch = to_fetch[:max_jobs]

    jobs = []
    for u in to_fetch:
        _time.sleep(0.4)
        if stats is not None:
            stats["fetches"] = stats.get("fetches", 0) + 1
        j = scrape_detail_page(u, employer_name=employer_name)
        if j is not None:
            jobs.append(j)
    return IncrementalResult(
        present=present, jobs=jobs, http=new_meta,
        complete=True, pages_crawled=1)


def _check_still_alive(present: dict[str, str], stored: dict[str, dict[str, Any]]) -> None:
    """Zero jobs where jobs used to live means the structure changed."""
    had_live = any(not r.get("vanished_at") for r in stored.values())
    if not present and had_live:
        raise ProfileStaleError("profile produced zero jobs where the site had jobs")


# ---- Greenhouse / Lever: one API call returns full content -----------------

def _api_platform_incremental(
    platform: str, params: dict[str, Any], listing_url: str,
    stored: dict[str, dict[str, Any]], *, employer_name: str, max_jobs: int,
    stats: Optional[dict[str, int]], http_meta: dict[str, Any],
) -> IncrementalResult:
    from scraper.universal import parse_greenhouse_jobs, parse_lever_jobs  # type: ignore

    if platform == "greenhouse":
        board = params.get("board")
        if not board:
            raise ProfileStaleError("no greenhouse board in profile")
        api = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    else:
        site = params.get("site")
        if not site:
            raise ProfileStaleError("no lever site in profile")
        api = f"https://api.lever.co/v0/postings/{site}?mode=json"

    resp, new_meta = conditional_get(api, http_meta, stats=stats)
    if resp is None:
        return IncrementalResult(not_modified=True, http=new_meta)
    if resp.status_code != 200:
        raise ProfileStaleError(f"{platform} API returned {resp.status_code}")
    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise ProfileStaleError(f"{platform} API returned non-JSON") from exc

    # Both APIs return the ENTIRE board in one response, so the only way this
    # census can be partial is the max_jobs cap truncating the parse.
    if platform == "greenhouse":
        raw_count = len((data.get("jobs") or [])) if isinstance(data, dict) else 0
    else:
        raw_count = len(data) if isinstance(data, list) else 0
    if platform == "greenhouse":
        all_jobs = parse_greenhouse_jobs(data, listing_url, employer_name=employer_name,
                                         max_jobs=max_jobs, board=board)
    else:
        all_jobs = parse_lever_jobs(data, listing_url, employer_name=employer_name,
                                    max_jobs=max_jobs, site=site)

    present: dict[str, str] = {}
    changed: list[Any] = []
    for j in all_jobs:
        if not j.source_url:
            continue
        fp = scraped_job_fingerprint(j)
        present[j.source_url] = fp
        row = stored.get(j.source_url)
        if row is None or row.get("vanished_at") or row.get("fingerprint") != fp:
            changed.append(j)
    _check_still_alive(present, stored)
    truncated = raw_count > len(all_jobs) or len(all_jobs) >= max_jobs
    return IncrementalResult(
        present=present, jobs=changed, http=new_meta,
        complete=not truncated,
        incomplete_reason="max_jobs_cap" if truncated else None,
    )


# ---- Workday: listing API pages, details only for new/changed --------------

def _workday_incremental(
    params: dict[str, Any], stored: dict[str, dict[str, Any]], *,
    employer_name: str, max_jobs: int, stats: Optional[dict[str, int]],
    http_meta: dict[str, Any],
) -> IncrementalResult:
    from scraper.base import ScrapedJob, strip_html  # type: ignore
    from scraper.universal import _money_string, _split_workday_location  # type: ignore

    tenant, wd, site = params.get("tenant"), params.get("wd"), params.get("site")
    if not (tenant and wd and site):
        raise ProfileStaleError("no workday tenant/site in profile")
    base = f"https://{tenant}.{wd}.myworkdayjobs.com"
    api = f"{base}/wday/cxs/{tenant}/{site}/jobs"
    validate_public_url(api)

    # 1. Listing pages only — title/location/postedOn per posting, no details.
    #    Walked to the LAST page (bounded): a partial census cannot be diffed
    #    for removals. max_jobs caps DETAIL fetches below, not the census.
    from app.skilled_pro.career_sources import MAX_LISTING_JOBS, MAX_LISTING_PAGES

    summaries: list[dict[str, Any]] = []
    offset, page_size, pages = 0, 20, 0
    complete, reason = True, None
    with httpx.Client(headers={"User-Agent": _UA, "Accept": "application/json",
                               "Content-Type": "application/json"},
                      timeout=_TIMEOUT) as client:
        while True:
            if pages >= MAX_LISTING_PAGES or len(summaries) >= MAX_LISTING_JOBS:
                complete, reason = False, "page_bound"
                break
            _count(stats)
            r = client.post(api, json={"searchText": "", "limit": page_size,
                                       "offset": offset, "appliedFacets": {}})
            if r.status_code != 200:
                if offset == 0:
                    raise ProfileStaleError(f"workday listing API returned {r.status_code}")
                complete, reason = False, "page_fetch_failed"
                break
            pages += 1
            postings = (r.json() or {}).get("jobPostings", []) or []
            if not postings:
                break
            summaries.extend(postings)
            if len(postings) < page_size:
                break
            offset += page_size

        present: dict[str, str] = {}
        to_fetch: list[tuple[str, dict[str, Any]]] = []
        deferred: list[str] = []
        for post in summaries:
            ep = post.get("externalPath", "")
            if not ep:
                continue
            detail_url = f"{base}{ep}"
            title = post.get("title") or ""
            loc = post.get("locationsText") or post.get("location") or ""
            fp = text_fingerprint(title, loc, str(post.get("postedOn") or ""))
            present[detail_url] = fp
            if _needs_detail(detail_url, fp, title, stored):
                if len(to_fetch) < max_jobs:
                    to_fetch.append((detail_url, post))
                else:
                    deferred.append(detail_url)
        _check_still_alive(present, stored)
        # Postings we saw but deliberately didn't fetch keep a NULL listing
        # fingerprint so the next sync still knows it owes them a detail fetch.
        for u in deferred:
            present[u] = None   # type: ignore[assignment]

        # 2. Detail fetches ONLY for new/changed postings.
        jobs: list[Any] = []
        for detail_url, post in to_fetch:
            ep = post.get("externalPath", "")
            title = post.get("title") or ""
            loc = post.get("locationsText") or post.get("location") or ""
            city, state = _split_workday_location(loc)
            try:
                _count(stats)
                det = client.get(f"{base}/wday/cxs/{tenant}/{site}/job{ep}", timeout=20.0)
                det_json = det.json() if det.status_code == 200 else {}
            except Exception:
                det_json = {}
            jp = det_json.get("jobPostingInfo", {}) if isinstance(det_json, dict) else {}
            jobs.append(ScrapedJob(
                title=title or jp.get("title", "Unknown"),
                employer_name=employer_name,
                source_url=detail_url,
                source_site=f"workday:{tenant}",
                city=city, state=state,
                description=strip_html(jp.get("jobDescription")),
                pay_raw=_money_string(jp.get("payRange") or jp.get("compensation")),
                posted_date=jp.get("postedOn") or post.get("postedOn"),
                employment_type=jp.get("timeType"),
                req_id=jp.get("jobReqId"),
            ))
    return IncrementalResult(present=present, jobs=jobs, http=http_meta,
                             complete=complete, incomplete_reason=reason,
                             pages_crawled=pages)


# ---- Generic careers pages: conditional listing + learned link patterns ----

def _generic_incremental(
    listing_url: str, profile: dict[str, Any], stored: dict[str, dict[str, Any]], *,
    employer_name: str, max_jobs: int, stats: Optional[dict[str, int]],
    http_meta: dict[str, Any],
) -> IncrementalResult:
    # Import via career_sources to reuse the exact same parsing brain.
    from scraper.trades import classify  # type: ignore

    from app.skilled_pro.career_sources import (
        _GENERIC_ANCHOR_TEXT,
        MAX_LISTING_JOBS,
        _looks_like_title,
        crawl_listing_pages,
        discover_job_links,
        parse_jsonld_jobpostings,
    )

    resp, new_meta = conditional_get(listing_url, http_meta, stats=stats)
    if resp is None:
        return IncrementalResult(not_modified=True, http=new_meta, complete=True)
    if resp.status_code >= 400:
        raise ProfileStaleError(f"listing page returned {resp.status_code}")
    html = resp.text

    # Walk the listing to its LAST page. A first-page-only crawl is not a
    # census of the site, and diffing one against stored postings reads every
    # posting below the fold as "removed".
    def fetch_page(page_url: str) -> Optional[str]:
        try:
            r = _guarded_get(page_url, stats=stats)
        except (BlockedURLError, httpx.HTTPError):
            return None
        return r.text if r.status_code < 400 else None

    pages, complete, reason = crawl_listing_pages(listing_url, html, fetch_page)

    # Path 1 — listing embeds full JobPosting JSON-LD: full data, zero extras.
    if profile.get("jsonld_listing"):
        all_jobs: list[Any] = []
        seen: set[str] = set()
        for page_url, page_html in pages:
            for j in parse_jsonld_jobpostings(page_html, page_url,
                                              employer_name=employer_name):
                if not j.source_url or j.source_url.rstrip("/") == listing_url.rstrip("/"):
                    continue
                if j.source_url in seen:
                    continue
                seen.add(j.source_url)
                all_jobs.append(j)
        present: dict[str, str] = {}
        changed: list[Any] = []
        for j in all_jobs:
            fp = scraped_job_fingerprint(j)
            present[j.source_url] = fp
            row = stored.get(j.source_url)
            if row is None or row.get("vanished_at") or row.get("fingerprint") != fp:
                changed.append(j)
        _check_still_alive(present, stored)
        if len(changed) > max_jobs:
            complete, reason = False, "max_jobs_cap"
            changed = changed[:max_jobs]
        return IncrementalResult(present=present, jobs=changed, http=new_meta,
                                 complete=complete, incomplete_reason=reason,
                                 pages_crawled=len(pages))

    # Path 2 — anchors filtered by the learned URL patterns.
    patterns = profile.get("link_patterns") or []
    links: list[tuple[str, str]] = []
    seen_links: set[str] = set()
    for page_url, page_html in pages:
        for u, t in discover_job_links(page_html, page_url):
            if u not in seen_links:
                seen_links.add(u)
                links.append((u, t))
    if patterns:
        matched = [(u, t) for u, t in links if url_matches_patterns(u, patterns)]
        # If the patterns filter everything away but anchors exist, the URL
        # scheme changed — fall back to the raw heuristic set this once.
        links = matched if matched else links
    if len(links) > MAX_LISTING_JOBS:
        complete, reason = False, "job_bound"
        links = links[:MAX_LISTING_JOBS]

    present = {}
    to_fetch: list[str] = []
    early_rejected = 0
    for link, anchor_text in links:
        fp = text_fingerprint(anchor_text or link)
        present[link] = fp
        if not _needs_detail(link, fp, anchor_text, stored):
            continue
        if len(to_fetch) >= max_jobs:
            # Seen on the site, detail fetch deferred to the next sync: leave
            # the listing fingerprint NULL so it is re-offered next time. The
            # census itself is still complete, so removals stay detectable.
            present[link] = None   # type: ignore[assignment]
            continue
        # Same cheap pre-fetch skip as the full path: an anchor that clearly
        # reads as a non-trades job title is counted, never fetched.
        text_l = (anchor_text or "").lower()
        if (
            anchor_text and len(anchor_text) >= 8
            and text_l not in _GENERIC_ANCHOR_TEXT
            and not classify(anchor_text).is_trade
            and _looks_like_title(anchor_text)
        ):
            early_rejected += 1
            continue
        to_fetch.append(link)
    _check_still_alive(present, stored)

    jobs = _fetch_details_parallel(to_fetch, listing_url, employer_name=employer_name,
                                   stats=stats)
    return IncrementalResult(present=present, jobs=jobs,
                             early_rejected=early_rejected, http=new_meta,
                             complete=complete, incomplete_reason=reason,
                             pages_crawled=len(pages))


def _fetch_details_parallel(
    urls: list[str], listing_url: str, *, employer_name: str,
    stats: Optional[dict[str, int]],
) -> list[Any]:
    """Fetch + parse detail pages for new/changed postings, in parallel."""
    if not urls:
        return []
    from scraper.base import ScrapedJob, strip_html  # type: ignore
    from scraper.extract import parse_sections  # type: ignore

    from app.skilled_pro.career_sources import (
        _extract_title_and_body,
        _location_from_page,
        parse_jsonld_jobpostings,
    )

    site = f"careers:{urlparse(listing_url).hostname or 'unknown'}"

    def fetch_one(link: str) -> Optional[Any]:
        try:
            resp = _guarded_get(link, stats=stats)
            if resp.status_code >= 400:
                return None
        except (BlockedURLError, httpx.HTTPError):
            return None
        detail_jobs = parse_jsonld_jobpostings(resp.text, link, employer_name=employer_name)
        if detail_jobs:
            job = detail_jobs[0]
            job.source_url = link
            return job
        title, body = _extract_title_and_body(resp.text)
        if not title:
            return None
        parsed = parse_sections(body)
        city, state = _location_from_page(body, link)
        return ScrapedJob(
            title=title, employer_name=employer_name, source_url=link, source_site=site,
            city=city, state=state,
            description=parsed.description or strip_html(body),
            responsibilities=parsed.responsibilities,
            requirements=parsed.requirements,
            qualifications=parsed.qualifications,
            pay_raw=parsed.pay_raw,
            experience_level=parsed.experience_level,
        )

    with ThreadPoolExecutor(max_workers=_DETAIL_WORKERS) as pool:
        results = list(pool.map(fetch_one, urls))
    return [j for j in results if j is not None]
