"""
Ford Motor Company careers scraper (TalentBrew / Radancy platform).
Scrapes HTML search results, then fetches JSON-LD from detail pages.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..base import BaseAdapter, ScrapedJob, normalize_state, strip_html, logger


class FordAdapter(BaseAdapter):
    site_name = "Ford Motor Company"
    base_url = "https://www.careers.ford.com"
    search_url = "https://www.careers.ford.com/search-jobs?orgIds=48560&kt=1&p={page}"

    def scrape_listings(self) -> list[dict[str, Any]]:
        """Paginate through HTML search results."""
        listings: list[dict[str, Any]] = []
        page = 1

        while True:
            url = self.search_url.format(page=page)
            soup = self._soup(url)

            items = soup.select("li.search-results-list__item")
            if not items:
                break

            for item in items:
                link = item.select_one("a.search-results-list__job-link")
                if not link:
                    continue

                job_id = link.get("data-job-id", "")
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = self.base_url + href

                loc_el = item.select_one("li.job-location")
                location_raw = loc_el.get_text(strip=True) if loc_el else ""

                city, state = _parse_ford_location(location_raw)

                listings.append({
                    "title": title,
                    "url": href,
                    "job_id": job_id,
                    "city": city,
                    "state": state,
                    "location_raw": location_raw,
                })

            total_match = re.search(r"(\d+)\s*Results", soup.get_text())
            total = int(total_match.group(1)) if total_match else 0

            logger.info(f"[Ford] Page {page}: {len(listings)}/{total} listings")

            if len(listings) >= total or len(items) == 0:
                break
            page += 1

        return listings

    def scrape_detail(self, listing: dict[str, Any]) -> Optional[ScrapedJob]:
        """Fetch detail page for JSON-LD structured data."""
        url = listing.get("url", "")
        if not url:
            return None

        try:
            soup = self._soup(url)
        except Exception:
            return self._from_listing(listing)

        ld_json = _extract_json_ld(soup)
        if ld_json:
            return _from_json_ld(ld_json, listing, url)

        return self._from_listing(listing)

    def _from_listing(self, listing: dict[str, Any]) -> ScrapedJob:
        return ScrapedJob(
            title=listing.get("title", "Unknown"),
            employer_name=self.site_name,
            source_url=listing.get("url", ""),
            source_site="ford",
            city=listing.get("city"),
            state=listing.get("state"),
        )


def _parse_ford_location(raw: str) -> tuple:
    """Parse 'City, State' from Ford location strings."""
    if not raw:
        return None, None
    parts = [p.strip() for p in raw.split(",")]
    city = parts[0] if parts else None
    state = normalize_state(parts[1]) if len(parts) > 1 else None
    return city, state


def _extract_json_ld(soup) -> Optional[dict]:
    """Extract JobPosting JSON-LD from detail page."""
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict) and data.get("@type") == "JobPosting":
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _from_json_ld(ld: dict, listing: dict, url: str) -> ScrapedJob:
    """Build ScrapedJob from Schema.org JobPosting JSON-LD."""
    title = ld.get("title", listing.get("title", "Unknown"))

    loc_data = ld.get("jobLocation", {})
    address = loc_data.get("address", {}) if isinstance(loc_data, dict) else {}
    city = address.get("addressLocality") or listing.get("city")
    state_raw = address.get("addressRegion") or listing.get("state")
    state = normalize_state(state_raw)
    country_raw = address.get("addressCountry", "US")
    country = country_raw if isinstance(country_raw, str) else "US"

    description = strip_html(ld.get("description"))

    posted = ld.get("datePosted")
    emp_type = ld.get("employmentType")

    salary = ld.get("baseSalary", {})
    pay_raw = None
    if isinstance(salary, dict):
        val = salary.get("value", {})
        if isinstance(val, dict):
            unit = val.get("unitText", "")
            min_v = val.get("minValue")
            max_v = val.get("maxValue")
            if min_v is not None:
                if max_v and max_v != min_v:
                    pay_raw = f"${min_v}-${max_v} {unit}".strip()
                else:
                    pay_raw = f"${min_v} {unit}".strip()

    org = ld.get("hiringOrganization", {})
    employer_name = org.get("name", "Ford Motor Company") if isinstance(org, dict) else "Ford Motor Company"
    identifier = ld.get("identifier", {})
    req_id = identifier.get("value") if isinstance(identifier, dict) else None

    return ScrapedJob(
        title=title,
        employer_name=employer_name,
        source_url=url,
        source_site="ford",
        city=city,
        state=state,
        country="US" if country in ("US", "USA", "United States") else country,
        description=description,
        posted_date=posted,
        employment_type=emp_type,
        pay_raw=pay_raw,
        req_id=req_id,
    )
