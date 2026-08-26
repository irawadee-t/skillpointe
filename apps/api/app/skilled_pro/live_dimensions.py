"""Per-dimension score breakdowns, computed at view time.

Why: the breakdown table (match_dimension_scores) was 9 rows per scored
pair — 19M rows / ~9 GB locally — warehoused against the possibility that
someone opens a match detail page. The engine is deterministic and scores
a single pair in well under a millisecond, so the breakdown is now
computed when it is actually viewed. Stored rows (from runs with
--store-dims, or history) are still preferred when present, so nothing
previously persisted changes behavior.

The single-pair inputs are fetched with the SAME functions the batch
pipeline uses wherever they accept an id filter, so column parity with
the audited engine inputs is structural, not copied.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REPO = None
for _parent in Path(__file__).resolve().parents:
    if (_parent / "scripts").is_dir() and (_parent / "packages").is_dir():
        _REPO = _parent
        break
if _REPO is not None:
    for _p in (str(_REPO / "packages"), str(_REPO / "scripts")):
        if _p not in sys.path:
            sys.path.insert(0, _p)

_DIM_SELECT = """
    SELECT dimension, weight, raw_score, weighted_score,
           rationale, null_handling_applied, null_handling_default
      FROM public.match_dimension_scores
     WHERE match_id = $1::uuid
     ORDER BY weighted_score DESC
"""


async def fetch_or_compute_dimensions(conn, match_id: str) -> list[dict[str, Any]]:
    """Stored breakdown rows if any exist; otherwise compute them live."""
    rows = await conn.fetch(_DIM_SELECT, match_id)
    if rows:
        return [dict(r) for r in rows]
    pair = await conn.fetchrow(
        "SELECT applicant_id::text AS aid, job_id::text AS jid "
        "FROM public.matches WHERE id = $1::uuid", match_id)
    if not pair:
        return []
    try:
        return await asyncio.to_thread(_compute_sync, pair["aid"], pair["jid"])
    except Exception:  # noqa: BLE001 - a breakdown must never 500 the page
        logger.exception("live dimension compute failed for match %s", match_id)
        return []


def _compute_sync(applicant_id: str, job_id: str) -> list[dict[str, Any]]:
    import recompute_matches as rm  # noqa: PLC0415 - scripts path set above
    from etl.db import get_connection
    from matching.engine import compute_match

    conn = get_connection()
    try:
        applicants = rm._fetch_applicants(conn, applicant_id=applicant_id)
        jobs = rm._fetch_jobs(conn, job_id=job_id)
        if not applicants or not jobs:
            return []
        app, job = applicants[0], jobs[0]
        config = rm._load_active_config(conn)
        employer = None
        if job.get("employer_id"):
            for e in rm._fetch_employers(conn):
                if str(e["id"]) == str(job["employer_id"]):
                    employer = e
                    break

        # Single-pair signal/credential/embedding rows, in the exact map
        # shapes the batch pipeline hands to the canonicalizer (column lists
        # mirror rm._fetch_* with an id filter added).
        with conn.cursor() as cur:
            cur.execute(
                """SELECT applicant_id, skills_extracted, certifications_extracted,
                          desired_job_families, work_style_signals, experience_signals,
                          readiness_signals, intent_signals, confidence_level,
                          review_status, embedding::text
                     FROM public.extracted_applicant_signals
                    WHERE applicant_id = %s AND review_status != 'overridden'
                    ORDER BY created_at DESC LIMIT 1""", (applicant_id,))
            r = cur.fetchone()
            a_sig, a_emb = {}, None
            if r:
                cols = [d[0] for d in cur.description]
                rec = dict(zip(cols, r))
                emb = rec.pop("embedding", None)
                a_sig = {applicant_id: rec}
                a_emb = rm._parse_vector(emb) if emb else None
            cur.execute(
                """SELECT job_id, required_skills, preferred_skills,
                          required_credentials, preferred_credentials,
                          job_family_signals, experience_signals,
                          work_style_signals, physical_requirement_signals,
                          confidence_level, review_status, embedding::text
                     FROM public.extracted_job_signals
                    WHERE job_id = %s AND review_status != 'overridden'
                    ORDER BY created_at DESC LIMIT 1""", (job_id,))
            r = cur.fetchone()
            j_sig, j_emb = None, None
            if r:
                cols = [d[0] for d in cur.description]
                rec = dict(zip(cols, r))
                emb = rec.pop("embedding", None)
                j_sig = rec
                j_emb = rm._parse_vector(emb) if emb else None
            cur.execute(
                """SELECT raw_name, canonical_code, canonical_name
                     FROM public.credentials WHERE applicant_id = %s""",
                (applicant_id,))
            creds = {applicant_id: [
                {"raw_name": rn, "canonical_code": cc, "canonical_name": cn}
                for rn, cc, cn in cur.fetchall()]}

        rm._canonicalize_credential_inputs(jobs, applicants, a_sig, creds)
        result = compute_match(
            app, job, employer, config,
            applicant_signals=a_sig.get(applicant_id),
            job_signals=j_sig,
            applicant_embedding=a_emb,
            job_embedding=j_emb,
        )
        dims = sorted(result.dimension_scores,
                      key=lambda d: d.weighted_score, reverse=True)
        return [{
            "dimension": d.dimension,
            "weight": d.weight,
            "raw_score": d.raw_score,
            "weighted_score": d.weighted_score,
            "rationale": d.rationale,
            "null_handling_applied": d.null_handling_applied,
            "null_handling_default": d.null_handling_default,
        } for d in dims]
    finally:
        conn.close()
