"""
Southwire careers scraper (SAP SuccessFactors platform).
Scrapes ALL positions from careers.southwire.com.
"""
from __future__ import annotations

from typing import Any, Optional

from ..base import BaseAdapter, ScrapedJob, parse_location, logger


class SouthwireAdapter(BaseAdapter):
    site_name = "Southwire"
    base_url = "https://careers.southwire.com"
    search_url = (
        "https://careers.southwire.com/search/?q="
        "&locationsearch=&startrow={offset}"
    )

    def scrape_listings(self) -> list[dict[str, Any]]:
        listings: list[dict[str, Any]] = []
        offset = 0
        page_size = 25

        while True:
            url = self.search_url.format(offset=offset)
            soup = self._soup(url)
            rows = soup.select("tr.data-row")

            if not rows:
                break

            for row in rows:
                link = row.select_one("a[href]")
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = self.base_url + href

                loc_span = row.select("td span.jobLocation")
                location_str = loc_span[0].get_text(strip=True) if loc_span else None

                date_span = row.select("td span.jobDate")
                date_str = date_span[0].get_text(strip=True) if date_span else None

                fac_span = row.select("td span.jobFacility")
                facility = fac_span[0].get_text(strip=True) if fac_span else None

                city, state = parse_location(location_str)

                listings.append({
                    "title": title,
                    "url": href,
                    "city": city,
                    "state": state,
                    "date": date_str,
                    "facility": facility,
                    "location_raw": location_str,
                })

            if len(rows) < page_size:
                break
            offset += page_size

        return listings

    def scrape_detail(self, listing: dict[str, Any]) -> Optional[ScrapedJob]:
        url = listing.get("url", "")
        if not url:
            return None

        try:
            soup = self._soup(url)
        except Exception:
            return self._from_listing(listing)

        desc_div = soup.select_one(".jobDisplay") or soup.select_one("#job-detail")
        description = desc_div.get_text(separator="\n", strip=True) if desc_div else None

        return ScrapedJob(
            title=listing.get("title", "Unknown"),
            employer_name=self.site_name,
            source_url=url,
            source_site="southwire",
            city=listing.get("city"),
            state=listing.get("state"),
            description=description,
            posted_date=listing.get("date"),
        )

    def _from_listing(self, listing: dict[str, Any]) -> ScrapedJob:
        return ScrapedJob(
            title=listing.get("title", "Unknown"),
            employer_name=self.site_name,
            source_url=listing.get("url", ""),
            source_site="southwire",
            city=listing.get("city"),
            state=listing.get("state"),
            posted_date=listing.get("date"),
        )
