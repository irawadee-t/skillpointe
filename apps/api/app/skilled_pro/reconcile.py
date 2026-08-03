"""
reconcile.py — enroll legacy scraped/imported jobs into career-source
fingerprint memory so listing syncs govern their lifecycle.

The ~390 jobs scraped before employer career sources existed live in
public.jobs with a source_url but are invisible to the incremental sync's
fingerprint memory (career_source_jobs) — so when their posting disappears
from the employer's site, nothing ever marks them stale. This module matches
each active job to a registered career source by URL (learned link patterns →
listing host → Workday tenant host → registrable domain) and enrolls it:

  1. a career_source_jobs row (first_seen_at = the job's created_at,
     fingerprint = hash of the STORED content) so the next listing sync can
     judge presence/absence and content drift, and
  2. a 'published' job_import_rows row in the source's rolling batch linked
     via published_job_id — the handle sync_rows uses to deactivate the live
     job when the posting vanishes (after the consecutive-miss grace).

Jobs whose URL matches NO registered source stay orphans; the tier-2
apply-link recheck keeps covering them. Matching requires the job to belong
to the SAME employer as the source — a URL-lookalike from another employer's
catalog is never claimed.

Pure matching helpers up top (unit-tested offline); DB orchestration below.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Optional
from urllib.parse import urlparse

from app.skilled_pro.career_profile import (
    scraped_job_fingerprint,
    url_matches_patterns,
)
from app.skilled_pro.career_sources import _ensure_batch, _parse_profile, _registrable

logger = logging.getLogger(__name__)


# ============================================================================
# Pure matching
# ============================================================================

def job_matches_source(
    job_url: str, *, listing_url: str, profile: Optional[dict[str, Any]] = None,
) -> bool:
    """Does this job's canonical posting URL belong to this careers source?

    Most-specific first: learned link patterns, exact listing host, the
    Workday tenant host from platform params, then same registrable domain
    (jobs.ball.com ↔ ball.com). Never matches across unrelated domains.
    """
    profile = profile or {}
    try:
        host = (urlparse(job_url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False

    patterns = profile.get("link_patterns") or []
    if patterns and url_matches_patterns(job_url, patterns):
        return True

    try:
        listing_host = (
            urlparse(profile.get("listing_url") or listing_url).hostname or ""
        ).lower()
    except ValueError:
        listing_host = ""
    if listing_host and host == listing_host:
        return True

    pp = profile.get("platform_params") or {}
    if pp.get("tenant") and pp.get("wd"):
        if host == f"{pp['tenant']}.{pp['wd']}.myworkdayjobs.com".lower():
            return True

    if listing_host and _registrable(host) == _registrable(listing_host):
        return True
    return False


_JOB_FP_MAP = {
    # ScrapedJob fingerprint field  ->  public.jobs column
    "title": "title_raw",
    "description": "description_raw",
    "responsibilities": "responsibilities_raw",
    "requirements": "requirements_raw",
    "qualifications": "preferred_qualifications_raw",
    "city": "city",
    "state": "state",
    "pay_raw": "pay_raw",
    "employment_type": "employment_type",
    "experience_level": "experience_level",
    "posted_date": "posted_date",
    "req_id": None,          # not stored on jobs — hashes as None
    "work_setting": "work_setting",
}


def job_row_fingerprint(row: dict[str, Any]) -> str:
    """Content fingerprint of a stored jobs row, shaped like a ScrapedJob's."""
    obj = SimpleNamespace(**{
        fp_field: (row.get(col) if col else None)
        for fp_field, col in _JOB_FP_MAP.items()
    })
    return scraped_job_fingerprint(obj)


# ============================================================================
# DB orchestration
# ============================================================================

_JOB_COLS_SQL = """
    SELECT j.id::text AS id, j.employer_id::text AS employer_id, j.source_url,
           j.title_raw, j.description_raw, j.responsibilities_raw,
           j.requirements_raw, j.preferred_qualifications_raw,
           j.city, j.state, j.country, j.pay_raw, j.employment_type,
           j.experience_level, j.posted_date::text AS posted_date,
           j.work_setting::text AS work_setting,
           j.created_at
      FROM public.jobs j
     WHERE j.is_active = TRUE
       AND j.source_url IS NOT NULL
       AND j.source_url ~* '^https?://'
"""


async def reconcile_legacy_jobs(conn) -> dict[str, Any]:
    """Match active URL-bearing jobs to registered career sources and enroll
    them in fingerprint memory + the source's rolling batch. Idempotent —
    already-enrolled jobs count as tracked, not re-enrolled."""
    sources = await conn.fetch(
        """
        SELECT s.*, e.name AS employer_name
          FROM public.employer_career_sources s
          JOIN public.employers e ON e.id = s.employer_id
         ORDER BY s.created_at
        """,
    )
    jobs = await conn.fetch(_JOB_COLS_SQL)

    claimed: set[str] = set()
    per_source: list[dict[str, Any]] = []

    for s in sources:
        source = dict(s)
        profile = _parse_profile(source.get("extraction_profile")) or {}
        matched = [
            dict(j) for j in jobs
            if j["id"] not in claimed
            and str(j["employer_id"]) == str(source["employer_id"])
            and job_matches_source(j["source_url"], listing_url=source["url"],
                                   profile=profile)
        ]
        enrolled = tracked = rows_created = rows_linked = 0
        if matched:
            batch_id = await _ensure_batch(conn, source, source.get("platform") or "generic")
            existing_rows = {
                r["source_url"]: r
                for r in await conn.fetch(
                    "SELECT id, source_url, published_job_id "
                    "FROM public.job_import_rows "
                    "WHERE batch_id = $1::uuid AND source_url IS NOT NULL",
                    batch_id,
                )
            }
            for j in matched:
                claimed.add(j["id"])
                inserted = await conn.fetchval(
                    """
                    INSERT INTO public.career_source_jobs
                        (source_id, source_url, title, fingerprint,
                         first_seen_at, last_seen_at, last_changed_at)
                    VALUES ($1::uuid, $2, $3, $4, $5, now(), $5)
                    ON CONFLICT (source_id, source_url) DO NOTHING
                    RETURNING id
                    """,
                    str(source["id"]), j["source_url"], j["title_raw"],
                    job_row_fingerprint(j), j["created_at"],
                )
                if inserted:
                    enrolled += 1
                else:
                    tracked += 1

                row = existing_rows.get(j["source_url"])
                if row is None:
                    await conn.execute(
                        """
                        INSERT INTO public.job_import_rows
                            (batch_id, title_raw, description_raw,
                             responsibilities_raw, requirements_raw,
                             preferred_qualifications_raw, city, state, country,
                             pay_raw, experience_level, employment_type,
                             posted_date, source_url, status, published_job_id)
                        VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8,
                                COALESCE($9, 'US'), $10, $11, $12, $13, $14,
                                'published', $15::uuid)
                        ON CONFLICT (batch_id, source_url)
                            WHERE source_url IS NOT NULL DO NOTHING
                        """,
                        batch_id, j["title_raw"], j["description_raw"],
                        j["responsibilities_raw"], j["requirements_raw"],
                        j["preferred_qualifications_raw"], j["city"], j["state"],
                        j["country"], j["pay_raw"], j["experience_level"],
                        j["employment_type"], j["posted_date"], j["source_url"],
                        j["id"],
                    )
                    rows_created += 1
                elif row["published_job_id"] is None:
                    await conn.execute(
                        "UPDATE public.job_import_rows SET published_job_id = $2::uuid, "
                        "status = 'published', updated_at = now() WHERE id = $1::uuid",
                        str(row["id"]), j["id"],
                    )
                    rows_linked += 1
        per_source.append({
            "source_id": str(source["id"]),
            "employer_name": source.get("employer_name"),
            "url": source["url"],
            "matched": len(matched),
            "enrolled": enrolled,
            "already_tracked": tracked,
            "rows_created": rows_created,
            "rows_linked": rows_linked,
        })

    orphans: dict[str, int] = {}
    for j in jobs:
        if j["id"] in claimed:
            continue
        host = (urlparse(j["source_url"]).hostname or "unknown").lower()
        orphans[host] = orphans.get(host, 0) + 1

    result = {
        "sources": per_source,
        "jobs_scanned": len(jobs),
        "jobs_enrolled": sum(x["enrolled"] for x in per_source),
        "jobs_already_tracked": sum(x["already_tracked"] for x in per_source),
        "orphans_total": sum(orphans.values()),
        "orphans_by_host": dict(sorted(orphans.items(), key=lambda kv: -kv[1])),
    }
    logger.info("Legacy-job reconciliation: %s", result)
    return result
