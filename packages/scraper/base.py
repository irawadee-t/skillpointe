"""
base.py — Base scraping adapter and shared data models.

All site-specific adapters inherit from BaseAdapter and implement
scrape_listings() and scrape_detail().
"""
from __future__ import annotations

import re
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple
from abc import ABC, abstractmethod

import httpx
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

US_STATE_FULL_TO_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}

US_STATE_ABBRS = set(US_STATE_FULL_TO_ABBR.values())


@dataclass
class ScrapedJob:
    """Standardized representation of a scraped job posting."""
    title: str
    employer_name: str
    source_url: str
    source_site: str

    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "US"

    description: Optional[str] = None
    requirements: Optional[str] = None
    qualifications: Optional[str] = None
    responsibilities: Optional[str] = None

    pay_raw: Optional[str] = None
    work_setting: Optional[str] = None
    experience_level: Optional[str] = None
    posted_date: Optional[str] = None
    job_category: Optional[str] = None
    employment_type: Optional[str] = None
    req_id: Optional[str] = None


class BaseAdapter(ABC):
    """Abstract base class for site-specific job scrapers."""

    site_name: str = ""
    base_url: str = ""
    search_url: str = ""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def _get(self, url: str) -> httpx.Response:
        """HTTP GET with polite delay."""
        time.sleep(self.delay)
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp

    def _soup(self, url: str) -> BeautifulSoup:
        resp = self._get(url)
        return BeautifulSoup(resp.text, "html.parser")

    @abstractmethod
    def scrape_listings(self) -> list[dict[str, Any]]:
        """Return a list of {title, url, location, ...} dicts from search pages."""

    def scrape_detail(self, listing: dict[str, Any]) -> Optional[ScrapedJob]:
        """Optionally scrape a detail page for richer data."""
        return ScrapedJob(
            title=listing.get("title", "Unknown"),
            employer_name=self.site_name,
            source_url=listing.get("url", ""),
            source_site=self.site_name.lower().replace(" ", "_"),
            city=listing.get("city"),
            state=listing.get("state"),
            posted_date=listing.get("date"),
            job_category=listing.get("category"),
        )

    def scrape_all(self) -> list[ScrapedJob]:
        """Full scrape: listings then details."""
        listings = self.scrape_listings()
        logger.info(f"[{self.site_name}] Found {len(listings)} listings")
        jobs: list[ScrapedJob] = []
        for i, listing in enumerate(listings):
            try:
                job = self.scrape_detail(listing)
                if job:
                    jobs.append(job)
                if (i + 1) % 25 == 0:
                    logger.info(f"[{self.site_name}] Scraped {i+1}/{len(listings)}")
            except Exception as e:
                logger.warning(f"[{self.site_name}] Failed to scrape {listing.get('url', '?')}: {e}")
        logger.info(f"[{self.site_name}] Completed: {len(jobs)} jobs scraped")
        return jobs


def parse_location(location_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Parse 'City, ST, US, ZIP' or 'City, ST' into (city, state)."""
    if not location_str:
        return None, None
    parts = [p.strip() for p in location_str.split(",")]
    city = parts[0] if parts else None
    state = None
    for p in parts[1:]:
        p = p.strip()
        if len(p) == 2 and p.isalpha() and p.upper() in US_STATE_ABBRS:
            state = p.upper()
            break
    return city, state


def normalize_state(raw: Optional[str]) -> Optional[str]:
    """Convert full state name or abbreviation to 2-letter code."""
    if not raw:
        return None
    raw = raw.strip()
    if len(raw) == 2 and raw.upper() in US_STATE_ABBRS:
        return raw.upper()
    abbr = US_STATE_FULL_TO_ABBR.get(raw.lower())
    return abbr


def strip_html(html_text: Optional[str]) -> Optional[str]:
    """Convert HTML to plain text."""
    if not html_text:
        return None
    soup = BeautifulSoup(html_text, "html.parser")
    return soup.get_text(separator="\n", strip=True)
