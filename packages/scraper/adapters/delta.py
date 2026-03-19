"""
Delta Air Lines careers scraper (Avature platform, AWS WAF protected).
Requires Playwright for headless browser rendering to bypass WAF.
Scrapes Technical Operations & Engineering jobs.
"""
from __future__ import annotations

import re
import json
import time
from typing import Any, Optional

from ..base import ScrapedJob, normalize_state, strip_html, logger, USER_AGENT

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class DeltaAdapter:
    """Delta scraper using Playwright (not inheriting BaseAdapter since it uses browser)."""

    site_name = "Delta Air Lines"
    base_url = "https://delta.avature.net"
    search_url = "https://delta.avature.net/en_US/careers/SearchJobs/?jobOffset={offset}"

    def __init__(self, delay: float = 2.0):
        self.delay = delay

    def close(self):
        pass

    def scrape_all(self) -> list[ScrapedJob]:
        if not HAS_PLAYWRIGHT:
            logger.error("[Delta] Playwright not installed — run: pip install playwright && python -m playwright install chromium")
            return []

        jobs: list[ScrapedJob] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()

            offset = 0
            total = None

            while True:
                url = self.search_url.format(offset=offset)
                logger.info(f"[Delta] Loading offset={offset}")

                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(3000)

                html = page.content()
                if total is None:
                    total_match = re.search(r"(\d+)-\d+\s+of\s+(\d+)", html)
                    if total_match:
                        total = int(total_match.group(2))
                        logger.info(f"[Delta] Total jobs: {total}")
                    else:
                        total_alt = re.search(r"of\s+(\d+)\s+results", html, re.I)
                        total = int(total_alt.group(1)) if total_alt else 0

                page_jobs = _parse_search_page(html)
                if not page_jobs:
                    logger.info(f"[Delta] No more jobs at offset={offset}")
                    break

                for j in page_jobs:
                    detail_url = j.get("url", "")
                    if detail_url:
                        try:
                            time.sleep(self.delay)
                            page.goto(detail_url, wait_until="networkidle", timeout=30000)
                            page.wait_for_timeout(2000)
                            detail_html = page.content()
                            job = _parse_detail_page(detail_html, j, detail_url)
                        except Exception as e:
                            logger.warning(f"[Delta] Detail page failed: {e}")
                            job = _from_listing(j)
                    else:
                        job = _from_listing(j)

                    if job:
                        jobs.append(job)

                logger.info(f"[Delta] Offset {offset}: {len(page_jobs)} jobs, total so far: {len(jobs)}")
                offset += 10
                time.sleep(self.delay)

                if total and offset >= total:
                    break

            browser.close()

        logger.info(f"[Delta] Completed: {len(jobs)} jobs scraped")
        return jobs


def _parse_search_page(html: str) -> list[dict[str, Any]]:
    """Extract job listings from Avature search page HTML."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    for item in soup.select("li.list__item"):
        link_el = item.select_one(".list__item__text__title a[href*='JobDetail']")
        if not link_el:
            continue

        title = link_el.get_text(strip=True)
        href = link_el.get("href", "")
        url = href if href.startswith("http") else f"https://delta.avature.net{href}"

        subtitle = item.select(".list__item__text__subtitle span")
        location_raw = subtitle[0].get_text(strip=True).rstrip(".") if len(subtitle) > 0 else ""
        ref_id = None
        if len(subtitle) > 1:
            ref_text = subtitle[1].get_text(strip=True)
            ref_id = ref_text.replace("Ref #", "").strip()

        city, state = _parse_delta_location(location_raw)

        jobs.append({
            "title": title,
            "url": url,
            "city": city,
            "state": state,
            "location_raw": location_raw,
            "ref_id": ref_id,
        })

    return jobs


def _parse_delta_location(raw: str) -> tuple:
    """Parse 'United States, Georgia, Atlanta' into (city, state)."""
    if not raw:
        return None, None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) >= 3 and "united states" in parts[0].lower():
        state = normalize_state(parts[1])
        city = parts[2] if len(parts) > 2 else None
        return city, state
    if len(parts) >= 2:
        return parts[0], normalize_state(parts[1])
    return None, None


def _parse_detail_page(html: str, listing: dict, url: str) -> Optional[ScrapedJob]:
    """Extract job details from Delta's Avature detail page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    details = soup.select("article.article--details")
    description_parts = []
    qualifications = None
    for detail in details:
        text = detail.get_text(separator="\n", strip=True)
        if not text or len(text) < 20:
            continue
        lower = text.lower()
        if "minimum qualifications" in lower or "what you need to succeed" in lower:
            qualifications = text
        elif "competitive edge" in lower or "preferred qualifications" in lower:
            pass
        elif "benefits" not in lower[:20]:
            description_parts.append(text)

    description = "\n\n".join(description_parts) if description_parts else None

    data_div = soup.select_one(".details--data")
    category = None
    posted_date = None
    if data_div:
        spans = data_div.select("span, div")
        texts = [s.get_text(strip=True) for s in spans if s.get_text(strip=True)]
        for t in texts:
            if re.match(r"\d{2}-\w{3}-\d{4}", t):
                posted_date = t
            elif t and not t.startswith("Ref") and "," not in t and len(t) < 30:
                category = t

    return ScrapedJob(
        title=listing.get("title", "Unknown"),
        employer_name="Delta Air Lines",
        source_url=url,
        source_site="delta",
        city=listing.get("city"),
        state=listing.get("state"),
        country="US",
        description=description,
        qualifications=qualifications,
        posted_date=posted_date or listing.get("date"),
        job_category=category,
        req_id=listing.get("ref_id"),
    )


def _from_listing(listing: dict) -> ScrapedJob:
    return ScrapedJob(
        title=listing.get("title", "Unknown"),
        employer_name="Delta Air Lines",
        source_url=listing.get("url", ""),
        source_site="delta",
        city=listing.get("city"),
        state=listing.get("state"),
        country="US",
        req_id=listing.get("ref_id"),
    )
