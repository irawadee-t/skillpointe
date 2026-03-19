"""
GE Vernova careers scraper (Paradox.ai / Workday).
Extracts job data from server-rendered __PRELOAD_STATE__ JSON in HTML.
US jobs only — filtered post-fetch since the SSR doesn't support country filters.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..base import BaseAdapter, ScrapedJob, normalize_state, logger


class GEVernovaAdapter(BaseAdapter):
    site_name = "GE Vernova"
    base_url = "https://careers.gevernova.com"
    search_url = "https://careers.gevernova.com/jobs?page_number={page}"

    def scrape_listings(self) -> list[dict[str, Any]]:
        """Paginate through all jobs, filtering to US only."""
        listings: list[dict[str, Any]] = []
        page = 1

        resp = self._get(self.search_url.format(page=1))
        data = _extract_preload(resp.text)
        if not data:
            logger.error("[GE Vernova] Could not extract __PRELOAD_STATE__")
            return []

        total = data.get("totalJob", 0)
        us_jobs = _filter_us(data.get("jobs", []))
        listings.extend(us_jobs)
        logger.info(f"[GE Vernova] Page 1: {len(us_jobs)} US jobs (total all: {total})")

        total_pages = (total + 9) // 10
        for page in range(2, total_pages + 1):
            try:
                resp = self._get(self.search_url.format(page=page))
                page_data = _extract_preload(resp.text)
                if not page_data:
                    break
                us_jobs = _filter_us(page_data.get("jobs", []))
                listings.extend(us_jobs)
                if page % 20 == 0:
                    logger.info(f"[GE Vernova] Page {page}/{total_pages}: {len(listings)} US jobs so far")
            except Exception as e:
                logger.warning(f"[GE Vernova] Page {page} failed: {e}")
                continue

        logger.info(f"[GE Vernova] Total US listings: {len(listings)}")
        return listings

    def scrape_detail(self, listing: dict[str, Any]) -> Optional[ScrapedJob]:
        """Convert pre-loaded JSON job into ScrapedJob."""
        title = listing.get("title", "")
        locations = listing.get("locations", [])
        loc = locations[0] if locations else {}

        city = loc.get("city")
        state = normalize_state(loc.get("stateAbbr") or loc.get("state"))
        is_remote = loc.get("isRemote", False) or listing.get("isRemote", False)

        slug = listing.get("slug", "")
        source_id = listing.get("sourceID", "")
        if slug:
            source_url = f"{self.base_url}/{slug}/job/{source_id}"
        else:
            source_url = f"{self.base_url}/jobs/{source_id}"

        emp_type_list = listing.get("employmentType", [])
        emp_type = emp_type_list[0] if emp_type_list else None
        if emp_type:
            emp_type = emp_type.replace("_", " ").title()

        extra_fields = listing.get("jobCardExtraFields", [])
        posted_date = None
        pay_type = None
        for ef in extra_fields:
            attr = ef.get("attribute_name", "")
            val = ef.get("value", "")
            if attr == "cf_posting_start_date" and val:
                posted_date = val
            elif attr == "cf_management_level" and val:
                pay_type = val

        work_setting = "remote" if is_remote else "on_site"

        return ScrapedJob(
            title=title,
            employer_name=self.site_name,
            source_url=source_url,
            source_site="ge_vernova",
            city=city,
            state=state,
            country="US",
            posted_date=posted_date,
            employment_type=emp_type,
            work_setting=work_setting,
            req_id=listing.get("requisitionID"),
        )

    def fetch_description(self, source_url: str) -> str | None:
        """Fetch the full job description from a detail page."""
        try:
            resp = self._get(source_url)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            desc_el = soup.select_one(".job-description")
            if desc_el:
                for btn in desc_el.select("script, style, .applyButton, .socialButtons"):
                    btn.decompose()
                text = desc_el.get_text(separator="\n", strip=True)
                text = re.sub(r"^Job Description\s*\n?", "", text).strip()
                return text if len(text) > 30 else None
            return None
        except Exception as e:
            logger.warning(f"[{self.site_name}] Failed to fetch description from {source_url}: {e}")
            return None

    def scrape_all(self) -> list[ScrapedJob]:
        listings = self.scrape_listings()
        logger.info(f"[{self.site_name}] Found {len(listings)} US listings")
        jobs: list[ScrapedJob] = []
        for i, listing in enumerate(listings):
            try:
                job = self.scrape_detail(listing)
                if job:
                    if job.source_url and not job.description:
                        job.description = self.fetch_description(job.source_url)
                    jobs.append(job)
                if (i + 1) % 50 == 0:
                    logger.info(f"[{self.site_name}] Processed {i + 1}/{len(listings)}")
            except Exception as e:
                logger.warning(f"[{self.site_name}] Failed to process listing: {e}")
        logger.info(f"[{self.site_name}] Completed: {len(jobs)} jobs")
        return jobs


def _extract_preload(html: str) -> Optional[dict]:
    match = re.search(r"window\.__PRELOAD_STATE__\s*=\s*({.*?});\s*$", html, re.S | re.M)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        return data.get("jobSearch", data)
    except json.JSONDecodeError:
        return None


def _filter_us(jobs: list[dict]) -> list[dict]:
    """Keep only jobs located in the United States."""
    us_jobs = []
    for j in jobs:
        locations = j.get("locations", [])
        if not locations:
            continue
        country = locations[0].get("country", "")
        if "United States" in country or country == "US":
            us_jobs.append(j)
    return us_jobs
