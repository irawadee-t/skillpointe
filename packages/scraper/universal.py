"""
universal.py — Platform-level adapters (one adapter per ATS, not per employer).

Each universal adapter takes a "careers URL" and ingests every public job
posting via the platform's documented JSON API (or stable HTML shell). Adding
a new employer on a supported platform requires ZERO new code — just point
the import wizard at their careers URL.

Currently implemented:
  • Workday        — /wday/cxs/{tenant}/{site}/jobs (POST search + GET detail)
  • Greenhouse     — boards-api.greenhouse.io/v1/boards/{board}/jobs
  • Lever          — api.lever.co/v0/postings/{site}

All return a list[ScrapedJob] in the same shape the rest of the pipeline expects.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .base import ScrapedJob, strip_html, normalize_state

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


# ============================================================================
# Workday
# ============================================================================
# Workday tenants live at `<tenant>.<wdN>.myworkdayjobs.com/<site>` and expose
# a JSON search API at `/wday/cxs/{tenant}/{site}/jobs`.

_WD_TENANT_SITE_RE = re.compile(
    r"https?://(?P<tenant>[^./]+)\.(?P<wd>wd[0-9]+)\.myworkdayjobs\.com/(?:en-US/)?(?P<site>[^/?#]+)",
    re.IGNORECASE,
)


def _parse_workday(url: str) -> Optional[tuple[str, str, str]]:
    m = _WD_TENANT_SITE_RE.search(url)
    if not m:
        return None
    return m.group("tenant"), m.group("wd"), m.group("site")


def scrape_workday(url: str, *, employer_name: str, max_jobs: int = 500) -> list[ScrapedJob]:
    parsed = _parse_workday(url)
    if not parsed:
        return []
    tenant, wd, site = parsed
    base = f"https://{tenant}.{wd}.myworkdayjobs.com"
    api  = f"{base}/wday/cxs/{tenant}/{site}/jobs"

    out: list[ScrapedJob] = []
    offset = 0
    page_size = 20
    with httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                               "Content-Type": "application/json"}, timeout=30.0) as client:
        while len(out) < max_jobs:
            r = client.post(api, json={"searchText": "", "limit": page_size,
                                       "offset": offset, "appliedFacets": {}})
            if r.status_code != 200:
                break
            data = r.json()
            postings = data.get("jobPostings", []) or []
            if not postings:
                break
            for post in postings:
                ep = post.get("externalPath", "")
                detail_url = f"{base}{ep}" if ep else url
                # Fetch detail for the description + structured fields.
                title = post.get("title") or ""
                location = post.get("locationsText") or post.get("location") or ""
                city, state = _split_workday_location(location)
                try:
                    det = client.get(f"{base}/wday/cxs/{tenant}/{site}/job{ep}", timeout=20.0)
                    det_json = det.json() if det.status_code == 200 else {}
                except Exception:
                    det_json = {}
                jp = det_json.get("jobPostingInfo", {}) if isinstance(det_json, dict) else {}
                description = strip_html(jp.get("jobDescription"))
                pay_raw = _money_string(jp.get("payRange") or jp.get("compensation"))
                posted = jp.get("postedOn") or post.get("postedOn")
                out.append(ScrapedJob(
                    title=title or jp.get("title", "Unknown"),
                    employer_name=employer_name,
                    source_url=detail_url,
                    source_site=f"workday:{tenant}",
                    city=city, state=state,
                    description=description,
                    pay_raw=pay_raw,
                    posted_date=posted,
                    employment_type=jp.get("timeType"),
                    req_id=jp.get("jobReqId"),
                ))
                if len(out) >= max_jobs:
                    break
            if len(postings) < page_size:
                break
            offset += page_size
    return out


def _split_workday_location(loc: str) -> tuple[Optional[str], Optional[str]]:
    if not loc:
        return None, None
    # "Detroit, MI, United States" / "United States-Detroit-MI" etc.
    parts = [p.strip() for p in re.split(r",|—|-", loc) if p.strip()]
    city = parts[0] if parts else None
    state = None
    for p in parts[1:]:
        s = normalize_state(p)
        if s:
            state = s
            break
    return city, state


def _money_string(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        return v if "$" in v else None
    if isinstance(v, dict):
        # Workday occasionally returns {"min":..., "max":..., "currency":"USD"}
        mn, mx = v.get("min") or v.get("minimum"), v.get("max") or v.get("maximum")
        if mn or mx:
            return f"${mn:,}{(' - $' + format(int(mx), ',')) if mx and mx != mn else ''}"
    return None


# ============================================================================
# Greenhouse
# ============================================================================
# Boards-API is public, paginated implicitly (all jobs in one call). The
# board token is in the URL: boards.greenhouse.io/{board}.

_GH_BOARD_RE = re.compile(r"boards\.greenhouse\.io/(?:embed/job_app\?for=)?(?P<board>[a-z0-9_-]+)", re.I)


def scrape_greenhouse(url: str, *, employer_name: str, max_jobs: int = 500) -> list[ScrapedJob]:
    m = _GH_BOARD_RE.search(url)
    if not m:
        # Vanity domain — try to fetch the page and look for the board token.
        try:
            page = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=20.0, follow_redirects=True)
            m = _GH_BOARD_RE.search(page.text)
        except Exception:
            return []
        if not m:
            return []
    board = m.group("board")
    api = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    try:
        r = httpx.get(api, headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                      timeout=30.0)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []
    return parse_greenhouse_jobs(data, url, employer_name=employer_name,
                                 max_jobs=max_jobs, board=board)


def parse_greenhouse_jobs(data: Any, url: str, *, employer_name: str,
                          max_jobs: int, board: str) -> list[ScrapedJob]:
    """Parse a boards-api /jobs?content=true payload into ScrapedJobs.

    Split out of scrape_greenhouse so an incremental sync can fetch the API
    itself (with conditional headers) and reuse the exact same parse."""
    out: list[ScrapedJob] = []
    for job in (data or {}).get("jobs", [])[:max_jobs]:
        loc = (job.get("location") or {}).get("name", "")
        city, state = _split_workday_location(loc)
        content_html = job.get("content")
        description = strip_html(content_html) if content_html else None
        offices = job.get("offices") or []
        if not city and offices:
            city = offices[0].get("name")
        out.append(ScrapedJob(
            title=job.get("title", "Unknown"),
            employer_name=employer_name,
            source_url=job.get("absolute_url") or url,
            source_site=f"greenhouse:{board}",
            city=city, state=state,
            description=description,
            posted_date=(job.get("updated_at") or job.get("created_at") or "")[:10] or None,
            req_id=str(job.get("id", "")),
        ))
    return out


# ============================================================================
# Lever
# ============================================================================
# Lever's public postings API: api.lever.co/v0/postings/{site}?mode=json

_LEVER_SITE_RE = re.compile(r"jobs\.lever\.co/(?P<site>[a-z0-9_-]+)", re.I)


def scrape_lever(url: str, *, employer_name: str, max_jobs: int = 500) -> list[ScrapedJob]:
    m = _LEVER_SITE_RE.search(url)
    if not m:
        return []
    site = m.group("site")
    api = f"https://api.lever.co/v0/postings/{site}?mode=json"
    try:
        r = httpx.get(api, headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                      timeout=30.0)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []
    return parse_lever_jobs(data, url, employer_name=employer_name,
                            max_jobs=max_jobs, site=site)


def parse_lever_jobs(data: Any, url: str, *, employer_name: str,
                     max_jobs: int, site: str) -> list[ScrapedJob]:
    """Parse a Lever v0/postings payload into ScrapedJobs (see
    parse_greenhouse_jobs for why this is split out)."""
    out: list[ScrapedJob] = []
    for post in (data or [])[:max_jobs]:
        cat = post.get("categories") or {}
        loc_str = cat.get("location") or ""
        city, state = _split_workday_location(loc_str)
        desc_plain = strip_html(post.get("descriptionPlain") or post.get("description"))
        # Lever splits "lists" — bullets per section (requirements, etc).
        sections = []
        for lst in post.get("lists", []):
            heading = lst.get("text", "").strip()
            items = strip_html(lst.get("content"))
            if heading and items:
                sections.append(f"{heading}\n{items}")
        full_desc = "\n\n".join(filter(None, [desc_plain] + sections))
        out.append(ScrapedJob(
            title=post.get("text", "Unknown"),
            employer_name=employer_name,
            source_url=post.get("hostedUrl") or url,
            source_site=f"lever:{site}",
            city=city, state=state,
            description=full_desc or None,
            employment_type=cat.get("commitment"),
            job_category=cat.get("team"),
            work_setting="remote" if "remote" in loc_str.lower() else None,
            req_id=post.get("id"),
        ))
    return out




# ============================================================================
# Cornerstone OnDemand (csod.com) — token-bootstrapped JSON API
# ============================================================================
# The career-site SPA at /ux/ats/careersite/{id}/home embeds a short-lived JWT
# in its HTML shell; that token + session cookies authorize the JSON search
# and jobDetails endpoints the SPA itself uses. One adapter serves EVERY
# Cornerstone-hosted employer (careerSiteId and corp name come from the URL).

_CSOD_URL_RE = re.compile(
    r"https?://(?P<host>[^/]+\.csod\.com)/ux/ats/careersite/(?P<site>\d+)/home",
    re.I,
)
_CSOD_TOKEN_RE = re.compile(r'"token"\s*:\s*"([^"]+)"')


def _parse_cornerstone(url: str) -> Optional[tuple[str, int, str]]:
    """(host, career_site_id, corp) from a csod careersite URL."""
    m = _CSOD_URL_RE.match(url or "")
    if not m:
        return None
    host = m.group("host")
    corp = host.split(".")[0]
    # honor an explicit ?c= corp override (some tenants use vanity hosts)
    cm = re.search(r"[?&]c=([\w-]+)", url)
    if cm:
        corp = cm.group(1)
    return host, int(m.group("site")), corp


def scrape_cornerstone(url: str, *, employer_name: str, max_jobs: int = 500) -> list[ScrapedJob]:
    parsed = _parse_cornerstone(url)
    if not parsed:
        return []
    host, site_id, corp = parsed
    base = f"https://{host}"

    out: list[ScrapedJob] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0,
                      follow_redirects=True) as client:
        # 1. Bootstrap: the SPA shell carries the JWT + sets session cookies.
        try:
            home = client.get(f"{base}/ux/ats/careersite/{site_id}/home", params={"c": corp})
            tok = _CSOD_TOKEN_RE.search(home.text or "")
        except Exception:
            return []
        if home.status_code != 200 or not tok:
            return []
        auth = {"Authorization": f"Bearer {tok.group(1)}",
                "Content-Type": "application/json"}

        # 2. Paginated search — same payload shape the SPA sends.
        page = 1
        page_size = 50
        while len(out) < max_jobs:
            try:
                r = client.post(f"{base}/services/x/career-site/v1/search",
                                headers=auth,
                                json={"careerSiteId": site_id, "careerSitePageId": site_id,
                                      "pageNumber": page, "pageSize": page_size,
                                      "cultureId": 1, "cultureName": "en-US",
                                      "searchText": "", "states": [], "countryCodes": [],
                                      "cities": [], "placeID": "", "radius": None,
                                      "postingsWithinDays": None,
                                      "customFieldCheckboxKeys": [],
                                      "customFieldDropdowns": [], "customFieldRadios": []})
            except Exception:
                break
            if r.status_code != 200:
                break
            reqs = ((r.json() or {}).get("data") or {}).get("requisitions") or []
            if not reqs:
                break
            for req in reqs:
                rid = req.get("requisitionId")
                if not rid:
                    continue
                title = req.get("displayJobTitle") or "Unknown"
                locs = req.get("locations") or []
                city = state = country = None
                if locs and isinstance(locs, list):
                    city = locs[0].get("city")
                    state = normalize_state(locs[0].get("state"))
                    country = locs[0].get("country")
                description = None
                try:
                    det = client.get(
                        f"{base}/services/x/job-requisition/v2/requisitions/{rid}/jobDetails",
                        params={"cultureId": 1}, headers=auth, timeout=20.0)
                    dd = ((det.json() or {}).get("data") or {}) if det.status_code == 200 else {}
                    description = strip_html(dd.get("externalDescription"))
                    prim = dd.get("primaryLocation") or {}
                    city = city or prim.get("city")
                    state = state or normalize_state(prim.get("state"))
                except Exception:
                    pass
                out.append(ScrapedJob(
                    title=title,
                    employer_name=employer_name,
                    source_url=(f"{base}/ux/ats/careersite/{site_id}/home/"
                                f"requisition/{rid}?c={corp}"),
                    source_site=f"cornerstone:{corp}",
                    city=city, state=state,
                    country=country or "US",
                    description=description,
                    posted_date=req.get("postingEffectiveDate"),
                    req_id=str(rid),
                ))
                if len(out) >= max_jobs:
                    break
            if len(reqs) < page_size:
                break
            page += 1
    return out


# ============================================================================
# Dispatch
# ============================================================================

def scrape_by_platform(platform: str, url: str, *, employer_name: str,
                       max_jobs: int = 500) -> list[ScrapedJob]:
    """Run the appropriate universal adapter. Returns [] if platform isn't yet
    implemented or the URL can't be parsed."""
    if platform == "workday":
        return scrape_workday(url, employer_name=employer_name, max_jobs=max_jobs)
    if platform == "greenhouse":
        return scrape_greenhouse(url, employer_name=employer_name, max_jobs=max_jobs)
    if platform == "lever":
        return scrape_lever(url, employer_name=employer_name, max_jobs=max_jobs)
    if platform == "cornerstone":
        return scrape_cornerstone(url, employer_name=employer_name, max_jobs=max_jobs)
    return []
