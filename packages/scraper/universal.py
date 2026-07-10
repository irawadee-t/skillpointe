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
    out: list[ScrapedJob] = []
    for job in data.get("jobs", [])[:max_jobs]:
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
    out: list[ScrapedJob] = []
    for post in data[:max_jobs]:
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
    return []
