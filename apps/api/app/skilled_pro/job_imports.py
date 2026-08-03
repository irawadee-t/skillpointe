"""
Helpers for the employer self-serve job-import workflow (pure-ish).

Lives in skilled_pro/ because it spans the worker side (jobs + matches) and the
existing import_runs infrastructure. The router is in app/routers/job_imports.py.
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path
from typing import Any, Optional

# packages/scraper lives outside apps/api. Add it to sys.path IF present.
# Walk only existing parents (avoids IndexError when the deploy layout is
# flatter than the repo — e.g. Railway Root Directory = apps/api).
for _parent in Path(__file__).resolve().parents:
    _pkg = _parent / "packages"
    if _pkg.is_dir():
        if str(_pkg) not in sys.path:
            sys.path.insert(0, str(_pkg))
        break


def parse_csv_rows(text: str) -> tuple[list[dict[str, Any]], int]:
    """Parse a CSV/TSV blob into normalized job-import rows. Returns (rows,
    skipped). Header is required. Recognised columns (case-insensitive):
      title (required), description, requirements, qualifications, responsibilities,
      city, state, country, work_setting, pay_min, pay_max, pay_type, pay_raw,
      experience_level, posted_date, source_url, employment_type, req_id.
    """
    if not text or not text.strip():
        return [], 0
    # Detect delimiter — comma vs. tab.
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)

    rows: list[dict[str, Any]] = []
    skipped = 0
    for raw in reader:
        norm = _normalize_csv_row(raw)
        if not norm or not norm.get("title_raw"):
            skipped += 1
            continue
        rows.append(norm)
    return rows, skipped


# Canonical → list of acceptable header spellings (case/whitespace-insensitive).
_HEADER_MAP: dict[str, tuple[str, ...]] = {
    "title_raw":            ("title", "job_title", "role", "position", "title_raw"),
    "description_raw":      ("description", "summary", "about", "overview", "description_raw"),
    "responsibilities_raw": ("responsibilities", "duties", "what_youll_do", "responsibilities_raw"),
    "requirements_raw":     ("requirements", "qualifications_required", "required", "requirements_raw"),
    "preferred_qualifications_raw": ("preferred", "preferred_qualifications", "nice_to_have", "preferred_qualifications_raw"),
    "city":                 ("city",),
    "state":                ("state", "state_code", "region"),
    "country":              ("country",),
    "work_setting":         ("work_setting", "remote", "on_site", "remote_setting"),
    "travel_requirement":   ("travel", "travel_requirement"),
    "pay_min":              ("pay_min", "min_pay", "salary_min", "min_salary"),
    "pay_max":              ("pay_max", "max_pay", "salary_max", "max_salary"),
    "pay_type":             ("pay_type", "salary_type"),
    "pay_raw":              ("pay", "salary", "compensation", "pay_raw"),
    "experience_level":     ("experience_level", "experience", "level", "seniority"),
    "posted_date":          ("posted_date", "posted", "date"),
    "employment_type":      ("employment_type", "type", "schedule"),
    "req_id":               ("req_id", "requisition_id", "job_id", "id"),
    "source_url":           ("source_url", "url", "link", "job_url"),
    "job_category":         ("category", "department", "team", "function"),
}


def _normalize_csv_row(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not raw:
        return None
    # Lowercase + replace spaces/hyphens with underscores for fuzzy match.
    lookup = {
        (k or "").strip().lower().replace(" ", "_").replace("-", "_"): (v or "").strip()
        for k, v in raw.items() if k is not None
    }
    out: dict[str, Any] = {}
    for canonical, aliases in _HEADER_MAP.items():
        for a in aliases:
            if a in lookup and lookup[a]:
                out[canonical] = lookup[a]
                break
    # Numeric coercions — leave None on parse failure.
    for k in ("pay_min", "pay_max"):
        if k in out:
            try:
                out[k] = float(str(out[k]).replace("$", "").replace(",", ""))
            except (TypeError, ValueError):
                out.pop(k, None)
    return out


def universal_scrape(url: str, *, employer_name: str, max_jobs: int = 500):
    """Detect the platform behind a careers URL and run the universal adapter.
    Returns (platform_str, list_of_ScrapedJob)."""
    from scraper.platform import Platform, detect_from_html, detect_from_url  # type: ignore
    from scraper.universal import scrape_by_platform  # type: ignore

    from app.util.net_guard import BlockedURLError, safe_get_sync, validate_public_url

    # SSRF guard: the URL is user-supplied. Reject internal/metadata targets
    # BEFORE any fetch (this also covers the subsequent scrape_by_platform call,
    # which fetches the same host).
    try:
        validate_public_url(url)
    except BlockedURLError:
        return "blocked", []

    platform = detect_from_url(url)
    if platform == Platform.UNKNOWN:
        # Fetch once and fingerprint the body — redirects re-validated per hop.
        try:
            r = safe_get_sync(url, timeout=15.0, headers={"User-Agent": "Mozilla/5.0"})
            platform = detect_from_html(r.text)
        except Exception:
            platform = Platform.UNKNOWN
    if platform == Platform.UNKNOWN:
        return "unknown", []
    jobs = scrape_by_platform(platform.value, url, employer_name=employer_name, max_jobs=max_jobs)
    return platform.value, jobs
