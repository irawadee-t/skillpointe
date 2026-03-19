"""
Schneider Electric careers scraper (Jibe / iCIMS platform).
Uses clean REST JSON API at careers.se.com/api/jobs.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ..base import BaseAdapter, ScrapedJob, normalize_state, strip_html, logger


class SchneiderAdapter(BaseAdapter):
    site_name = "Schneider Electric"
    base_url = "https://careers.se.com"
    api_url = "https://careers.se.com/api/jobs"

    def __init__(self, delay: float = 0.5):
        super().__init__(delay=delay)
        self.client.headers["Accept"] = "application/json"

    def scrape_listings(self) -> list[dict[str, Any]]:
        """Fetch all US jobs via JSON API (paginated, 10 per page)."""
        listings: list[dict[str, Any]] = []
        page = 1

        while True:
            resp = self._get(
                f"{self.api_url}?keywords=&country=United+States"
                f"&page={page}&sortBy=relevance&descending=false&internal=false"
            )
            data = resp.json()
            total = data.get("totalCount", 0)
            jobs = data.get("jobs", [])

            if not jobs:
                break

            for item in jobs:
                j = item.get("data", item)
                listings.append(j)

            logger.info(f"[Schneider] Page {page}: {len(listings)}/{total} jobs")

            if len(listings) >= total:
                break
            page += 1

        return listings

    def scrape_detail(self, listing: dict[str, Any]) -> Optional[ScrapedJob]:
        """Convert API response to ScrapedJob — no detail page needed."""
        title = listing.get("title", "")
        req_id = listing.get("req_id", "")
        slug = listing.get("slug", req_id)

        job_id = listing.get("id", slug)
        source_url = f"{self.base_url}/jobs/{job_id}"

        city = listing.get("city")
        state_raw = listing.get("state")
        state = normalize_state(state_raw)
        country = listing.get("country", "US")

        description = strip_html(listing.get("description"))
        qualifications = strip_html(listing.get("qualifications"))
        responsibilities = strip_html(listing.get("responsibilities"))

        categories = listing.get("categories", [])
        category = categories[0].get("name", "") if categories else None

        posted = listing.get("posted_date")
        emp_type = listing.get("employment_type")

        tags2 = listing.get("tags2", [])
        experience = tags2[0] if tags2 else None

        work_setting_raw = listing.get("location_type", "")
        work_setting = _map_work_setting(work_setting_raw)

        return ScrapedJob(
            title=title,
            employer_name=self.site_name,
            source_url=source_url,
            source_site="schneider_electric",
            city=city,
            state=state,
            country="US",
            description=description,
            qualifications=qualifications,
            responsibilities=responsibilities,
            posted_date=posted,
            job_category=category,
            employment_type=emp_type,
            experience_level=experience,
            work_setting=work_setting,
            req_id=req_id,
        )


def _map_work_setting(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    r = raw.lower()
    if "remote" in r:
        return "remote"
    if "hybrid" in r:
        return "hybrid"
    if "onsite" in r or "on-site" in r or "on_site" in r:
        return "on_site"
    return None
