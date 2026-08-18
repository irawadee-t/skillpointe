#!/usr/bin/env python3
"""
recompute_matches.py — Phase 5: Match recomputation pipeline.

Fetches applicants and jobs from Supabase, runs the deterministic matching
engine, and upserts results into the matches + match_dimension_scores tables.

Prerequisites:
  1. normalize_data.py must have been run (canonical_job_family_id populated)
  2. Local Supabase must be running: supabase start

Usage:
  # Full recompute — all active applicants × all active jobs
  python scripts/recompute_matches.py

  # Single applicant (useful for debugging)
  python scripts/recompute_matches.py --applicant-id <uuid>

  # Single job
  python scripts/recompute_matches.py --job-id <uuid>

  # Limit to first N applicants × N jobs (fast smoke test)
  python scripts/recompute_matches.py --limit 10

  # Dry-run: compute but do not write to DB
  python scripts/recompute_matches.py --dry-run

  # Verbose: print score breakdowns during run
  python scripts/recompute_matches.py --verbose

For a full run with 335 applicants × 300 jobs = 100,500 pairs.
Expect ~2–5 min on local hardware with no parallelism.

See BUILD_PLAN.md §7 (Early Data / Ranking Validation Rule).
"""
import argparse
import json
import sys
import uuid
from datetime import date
from pathlib import Path

# Allow importing from packages/
sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))

from matching.config import load_config
from matching.engine import MatchResult, compute_match


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recompute all applicant-job matches"
    )
    parser.add_argument("--applicant-id", default=None,
                        help="Only recompute matches for this applicant UUID")
    parser.add_argument("--job-id", default=None,
                        help="Only recompute matches for this job UUID")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit applicants AND jobs to first N each (testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write to DB")
    parser.add_argument("--verbose", action="store_true",
                        help="Print score breakdowns")
    parser.add_argument("--prefilter", action="store_true",
                        help="Candidate generation for large pools: score only "
                             "same-state pairs whose fields share a sector (or "
                             "either side has no field). Pairs outside the "
                             "filter would gate out as ineligible anyway and "
                             "are not stored.")
    parser.add_argument("--skip-geocode", action="store_true",
                        help="Skip the coordinate backfill step (offline runs)")
    args = parser.parse_args()

    # ----------------------------------------------------------------
    # Connect + load config
    # ----------------------------------------------------------------
    try:
        from etl.db import get_connection
    except ImportError:
        from etl.db import get_connection

    try:
        conn = get_connection()
    except Exception as e:
        print(f"ERROR connecting to DB: {e}")
        print("Is Supabase running?  Run: supabase start")
        return 1

    config = _load_active_config(conn)
    print(f"Loaded policy config version: {config.version}")

    # ----------------------------------------------------------------
    # Clean up stale matches for deactivated jobs
    # ----------------------------------------------------------------
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM public.matches
        WHERE job_id IN (SELECT id FROM public.jobs WHERE is_active = FALSE)
    """)
    stale_count = cur.rowcount
    if stale_count:
        conn.commit()
        print(f"Cleaned up {stale_count} stale matches for deactivated jobs")

    # ----------------------------------------------------------------
    # Fetch applicants + jobs + extracted signals
    # ----------------------------------------------------------------
    applicants = _fetch_applicants(conn, applicant_id=args.applicant_id, limit=args.limit)
    jobs = _fetch_jobs(conn, job_id=args.job_id, limit=args.limit)
    employers = _fetch_employers(conn)

    # Resolve missing home/job-city coordinates (geocode_cache first, then a
    # rate-limited Nominatim lookup for unseen cities). The engine itself
    # stays pure — it just consumes lat/lng off the input dicts. Network
    # failures degrade gracefully to state/region gating.
    if not args.skip_geocode:
        _backfill_coords(conn, applicants, jobs)

    employer_map = {str(e["id"]): e for e in employers}

    # Phase 7: load extracted signals and embeddings
    app_signals_map = _fetch_applicant_signals(conn)
    job_signals_map = _fetch_job_signals(conn)
    app_embedding_map = _fetch_applicant_embeddings(conn)
    job_embedding_map = _fetch_job_embeddings(conn)

    # Credential taxonomy prep (data-side only — the engine stays untouched):
    # job required-cert strings are swapped for their canonical display names
    # (from jobs.required_credentials_canonical, written by
    # scripts/backfill_credential_taxonomy.py), and applicants' structured
    # credentials rows are merged into certifications_extracted under their
    # canonical names — so both sides of the credential gate meet on canonical
    # strings instead of raw-string luck.
    app_credentials_map = _fetch_applicant_credentials(conn)
    _canonicalize_credential_inputs(jobs, applicants, app_signals_map, app_credentials_map)

    print(f"Extracted signals: {len(app_signals_map)} applicants, {len(job_signals_map)} jobs")
    print(f"Embeddings: {len(app_embedding_map)} applicants, {len(job_embedding_map)} jobs")

    # Candidate generation (--prefilter): same state + sector-plausible.
    # 43k applicants x 400 jobs = 17M raw pairs; storing gate-fail rows at
    # that scale is pure ballast. Sector plausibility mirrors the family
    # gate exactly (sn_taxonomy.relate != "unrelated"), so nothing that
    # could score above ineligible is ever skipped.
    from matching import sn_taxonomy as _snt

    def _candidates(app: dict) -> list[dict]:
        if not args.prefilter:
            return jobs
        a_state = (app.get("state") or "").upper()
        if not a_state:
            return []          # no geography signal; profile stays match-less for now
        a_code = app.get("canonical_job_family_code")
        out = []
        for j in jobs:
            if (j.get("state") or "").upper() != a_state and (j.get("work_setting") or "") != "remote":
                continue
            j_code = j.get("canonical_job_family_code")
            if a_code and j_code and _snt.relate(a_code, j_code) == "unrelated":
                continue
            out.append(j)
        return out

    if args.prefilter:
        total_pairs = sum(len(_candidates(a)) for a in applicants)
        print(f"Applicants: {len(applicants)}, Jobs: {len(jobs)}, "
              f"prefiltered pairs: {total_pairs}")
    else:
        total_pairs = len(applicants) * len(jobs)
        print(f"Applicants: {len(applicants)}, Jobs: {len(jobs)}, Pairs: {total_pairs}")
    if args.dry_run:
        print("(DRY RUN — no data will be written)\n")

    # ----------------------------------------------------------------
    # Scoring run metadata
    # ----------------------------------------------------------------
    run_id = str(uuid.uuid4())
    run_date = date.today().isoformat()
    print(f"Scoring run ID: {run_id}\n")

    # ----------------------------------------------------------------
    # Compute matches
    # ----------------------------------------------------------------
    counters = {"total": 0, "eligible": 0, "near_fit": 0, "ineligible": 0,
                "error": 0, "strong_fit": 0, "good_fit": 0}

    BATCH = 500  # commit every N rows

    for app in applicants:
        app_id = str(app["id"])
        a_sig = app_signals_map.get(app_id)
        a_emb = app_embedding_map.get(app_id)

        for job in _candidates(app):
            job_id_str = str(job["id"])
            emp = employer_map.get(str(job.get("employer_id")), {})
            j_sig = job_signals_map.get(job_id_str)
            j_emb = job_embedding_map.get(job_id_str)

            try:
                result = compute_match(
                    app, job, emp, config,
                    today=date.today(),
                    scoring_run_id=run_id,
                    applicant_signals=a_sig,
                    job_signals=j_sig,
                    applicant_embedding=a_emb,
                    job_embedding=j_emb,
                )
                counters["total"] += 1
                counters[result.eligibility_status] = counters.get(result.eligibility_status, 0) + 1
                counters[result.match_label] = counters.get(result.match_label, 0) + 1

                if args.verbose:
                    _print_match(result, app, job)

                if not args.dry_run:
                    _upsert_match(conn, result)

                    if counters["total"] % BATCH == 0:
                        conn.commit()
                        print(f"  ... {counters['total']}/{total_pairs} committed")

            except Exception as e:
                counters["error"] += 1
                if args.verbose:
                    print(f"  ERROR app={app['id']!s:.8} job={job['id']!s:.8}: {e}")

    if not args.dry_run:
        conn.commit()
    conn.close()

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    print()
    print("=" * 60)
    print(f"  Recompute summary: {run_date}{'  [DRY RUN]' if args.dry_run else ''}")
    print("=" * 60)
    print(f"  Total pairs:    {counters['total']}")
    print(f"  Eligible:       {counters.get('eligible', 0)}")
    print(f"  Near-fit:       {counters.get('near_fit', 0)}")
    print(f"  Ineligible:     {counters.get('ineligible', 0)}")
    print(f"  Strong fit:     {counters.get('strong_fit', 0)}")
    print(f"  Good fit:       {counters.get('good_fit', 0)}")
    print(f"  Errors:         {counters['error']}")
    print(f"  Run ID:         {run_id}")
    print()
    return 0 if counters["error"] == 0 else 1


# ---------------------------------------------------------------------------
# Coordinate backfill — geocode_cache first, Nominatim for unseen cities.
# Mirrors apps/api/app/skilled_pro/geocode.py (same normalization + provider)
# but synchronous, since this script runs on psycopg2 outside the API.
# ---------------------------------------------------------------------------

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_UA = "SkillPointe-Match/0.1 (trades-workforce-platform; support@skillpointe.local)"


def _geo_normalize(city: str = "", state: str = "", zip_code: str = "") -> str:
    parts = []
    if zip_code and zip_code.strip():
        parts.append(zip_code.strip())
    if city and city.strip():
        parts.append(city.strip().lower())
    if state and state.strip():
        parts.append(state.strip().upper()[:2])
    return ", ".join(parts)


def _backfill_coords(conn, applicants: list[dict], jobs: list[dict]) -> None:
    """Fill lat/lng on applicant/job dicts (and persist to their rows).

    1. Collect rows missing coords that have a city or state.
    2. Resolve each distinct normalized query via geocode_cache.
    3. For cache misses, hit Nominatim at <= 1 req/sec, memoizing results.
    4. Write resolved coords back onto public.applicants / public.jobs.
    """
    import time

    pending: dict[str, list[tuple[str, dict]]] = {}  # query -> [(table, row_dict)]
    for table, rows in (("applicants", applicants), ("jobs", jobs)):
        for r in rows:
            if r.get("lat") is not None and r.get("lng") is not None:
                continue
            q = _geo_normalize(r.get("city") or "", r.get("state") or "")
            if q:
                pending.setdefault(q, []).append((table, r))
    if not pending:
        return

    # Cache lookups
    resolved: dict[str, tuple[float, float]] = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT query, lat, lng FROM public.geocode_cache WHERE query = ANY(%s)",
            (list(pending.keys()),),
        )
        for q, lat, lng in cur.fetchall():
            resolved[q] = (float(lat), float(lng))

    misses = [q for q in pending if q not in resolved]
    if misses:
        try:
            import httpx
        except ImportError:
            httpx = None
        if httpx is not None:
            print(f"Geocoding {len(misses)} unseen locations via Nominatim (~1/sec)...")
            for q in misses:
                try:
                    resp = httpx.get(
                        _NOMINATIM_URL,
                        params={"q": q, "format": "json", "limit": 1,
                                "countrycodes": "us", "addressdetails": 0},
                        headers={"User-Agent": _NOMINATIM_UA},
                        timeout=8.0,
                    )
                    if resp.status_code == 200 and resp.json():
                        hit = resp.json()[0]
                        lat, lng = float(hit["lat"]), float(hit["lon"])
                        resolved[q] = (lat, lng)
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO public.geocode_cache
                                    (query, lat, lng, display_name, provider)
                                VALUES (%s, %s, %s, %s, 'nominatim')
                                ON CONFLICT (query) DO NOTHING
                                """,
                                (q, lat, lng, hit.get("display_name", "")),
                            )
                        conn.commit()
                except Exception as e:
                    print(f"  geocode failed for {q!r}: {e}")
                time.sleep(1.05)  # Nominatim fair-use: 1 req/sec

    # Attach coords to in-memory rows + persist onto entity rows
    updated = {"applicants": 0, "jobs": 0}
    with conn.cursor() as cur:
        for q, targets in pending.items():
            coords = resolved.get(q)
            if not coords:
                continue
            for table, row in targets:
                row["lat"], row["lng"] = coords
                cur.execute(
                    f"UPDATE public.{table} SET lat = %s, lng = %s WHERE id = %s",
                    (coords[0], coords[1], str(row["id"])),
                )
                updated[table] += 1
    conn.commit()
    if updated["applicants"] or updated["jobs"]:
        print(f"Coordinates backfilled: {updated['applicants']} applicants, "
              f"{updated['jobs']} jobs ({len(resolved)}/{len(pending)} locations resolved)")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _load_active_config(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT config FROM public.policy_configs WHERE is_active = TRUE LIMIT 1"
        )
        row = cur.fetchone()
    if row:
        # config is stored as JSONB — convert to YAML-compatible dict
        cfg_dict = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        from matching.config import _from_yaml
        return _from_yaml(cfg_dict)
    return load_config()


def _fetch_applicants(conn, applicant_id=None, limit=None) -> list[dict]:
    where = "WHERE 1=1"
    params = []
    if applicant_id:
        where += " AND a.id = %s"
        params.append(applicant_id)
    lim = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT
            a.id, a.first_name, a.last_name, a.program_name_raw,
            a.state, a.region, a.city,
            a.willing_to_relocate, a.willing_to_travel, a.commute_radius_miles,
            a.lat, a.lng,
            a.experience_raw, a.bio_raw, a.career_goals_raw,
            -- Structured input for the seniority gate. Without this the gate
            -- read a missing key, saw None, and treated every applicant as
            -- having zero years.
            a.years_experience,
            a.expected_completion_date, a.available_from_date,
            a.travel_preference::text, a.relocation_preference::text,
            a.relocation_states,
            a.has_internship, a.internship_details,
            a.essay_background, a.essay_impact,
            a.enrollment_status::text, a.career_path, a.program_field,
            jf.code AS canonical_job_family_code,
            a.degree_type::text, a.school_name, a.specific_career
        FROM public.applicants a
        LEFT JOIN public.canonical_job_families jf ON jf.id = a.canonical_job_family_id
        {where}
        ORDER BY a.created_at
        {lim}
    """
    with conn.cursor() as cur:
        cur.execute(sql, params or None)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _fetch_jobs(conn, job_id=None, limit=None) -> list[dict]:
    where = "WHERE j.is_active = TRUE"
    params = []
    if job_id:
        where += " AND j.id = %s"
        params.append(job_id)
    lim = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT
            j.id, j.employer_id,
            j.title_raw, j.title_normalized, j.description_raw,
            j.requirements_raw, j.preferred_qualifications_raw,
            j.state, j.region, j.city,
            j.lat, j.lng,
            j.work_setting, j.travel_requirement,
            j.pay_min, j.pay_max, j.pay_type, j.pay_raw,
            j.required_credentials,
            j.required_credentials_canonical,
            j.experience_level,
            jf.code AS canonical_job_family_code,
            j.required_experience_years
        FROM public.jobs j
        LEFT JOIN public.canonical_job_families jf ON jf.id = j.canonical_job_family_id
        {where}
        ORDER BY j.created_at
        {lim}
    """
    with conn.cursor() as cur:
        cur.execute(sql, params or None)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _fetch_employers(conn) -> list[dict]:
    sql = "SELECT id, name, is_partner FROM public.employers"
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _fetch_applicant_credentials(conn) -> dict[str, list[dict]]:
    """Structured credentials per applicant (manual adds, SIS ingest,
    OCR/badge-verified). Keyed by applicant_id."""
    sql = """
        SELECT applicant_id, raw_name, canonical_code, canonical_name
        FROM public.credentials
    """
    out: dict[str, list[dict]] = {}
    with conn.cursor() as cur:
        cur.execute(sql)
        for applicant_id, raw_name, code, name in cur.fetchall():
            out.setdefault(str(applicant_id), []).append(
                {"raw_name": raw_name, "canonical_code": code, "canonical_name": name}
            )
    return out


def _canonicalize_credential_inputs(
    jobs: list[dict],
    applicants: list[dict],
    app_signals_map: dict[str, dict],
    app_credentials_map: dict[str, list[dict]],
) -> None:
    """Data-prep canonicalization for the credential gate (engine untouched).

    Job side: each required_credentials entry is replaced by its canonical
    display name when the stored normalizer output was confident. The list
    length never changes, so gate semantics (count of required creds) are
    preserved — only the surface strings are normalized. Raw strings in the
    DB are never modified.

    Applicant side: credentials-table rows are appended to the
    certifications_extracted signal (canonical name first, raw name kept) so
    verified/manual credentials participate in gating even for applicants
    with no LLM extraction. Applicants with neither signals nor credentials
    keep a None signal — "unknown", not "has none".
    """
    for job in jobs:
        canon = job.get("required_credentials_canonical")
        reqs = job.get("required_credentials")
        if not canon or not reqs or not isinstance(canon, list):
            continue
        by_raw = {c.get("raw"): c for c in canon if isinstance(c, dict)}
        job["required_credentials"] = [
            ((by_raw.get(r) or {}).get("name") or r) if (by_raw.get(r) or {}).get("confident") else r
            for r in reqs
        ]

    for app in applicants:
        app_id = str(app["id"])
        creds = app_credentials_map.get(app_id)
        if not creds:
            continue
        sig = dict(app_signals_map.get(app_id) or {})
        items = list(sig.get("certifications_extracted") or [])
        seen = {
            str(i.get("name") or i.get("cert_name") or "").strip().lower()
            for i in items if isinstance(i, dict)
        }
        for c in creds:
            for nm in (c.get("canonical_name"), c.get("raw_name")):
                if not nm or nm.strip().lower() in seen:
                    continue
                seen.add(nm.strip().lower())
                items.append({
                    "name": nm,
                    "canonical_slug": c.get("canonical_code"),
                    "source": "credentials_table",
                })
        sig["certifications_extracted"] = items
        app_signals_map[app_id] = sig


def _fetch_applicant_signals(conn) -> dict[str, dict]:
    """Load latest extracted signals per applicant (keyed by applicant_id)."""
    sql = """
        SELECT DISTINCT ON (applicant_id)
            applicant_id,
            skills_extracted,
            certifications_extracted,
            desired_job_families,
            work_style_signals,
            experience_signals,
            readiness_signals,
            intent_signals,
            confidence_level,
            review_status
        FROM public.extracted_applicant_signals
        WHERE review_status != 'overridden'
        ORDER BY applicant_id, created_at DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return {str(r["applicant_id"]): r for r in rows}


def _fetch_job_signals(conn) -> dict[str, dict]:
    """Load latest extracted signals per job (keyed by job_id)."""
    sql = """
        SELECT DISTINCT ON (job_id)
            job_id,
            required_skills,
            preferred_skills,
            required_credentials,
            preferred_credentials,
            job_family_signals,
            experience_signals,
            work_style_signals,
            physical_requirement_signals,
            confidence_level,
            review_status
        FROM public.extracted_job_signals
        WHERE review_status != 'overridden'
        ORDER BY job_id, created_at DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return {str(r["job_id"]): r for r in rows}


def _fetch_applicant_embeddings(conn) -> dict[str, list[float]]:
    """Load embeddings per applicant (keyed by applicant_id)."""
    sql = """
        SELECT DISTINCT ON (applicant_id)
            applicant_id, embedding::text
        FROM public.extracted_applicant_signals
        WHERE embedding IS NOT NULL AND review_status != 'overridden'
        ORDER BY applicant_id, created_at DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        result = {}
        for row in cur.fetchall():
            app_id = str(row[0])
            emb_str = row[1]
            if emb_str:
                result[app_id] = _parse_vector(emb_str)
        return result


def _fetch_job_embeddings(conn) -> dict[str, list[float]]:
    """Load embeddings per job (keyed by job_id)."""
    sql = """
        SELECT DISTINCT ON (job_id)
            job_id, embedding::text
        FROM public.extracted_job_signals
        WHERE embedding IS NOT NULL AND review_status != 'overridden'
        ORDER BY job_id, created_at DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        result = {}
        for row in cur.fetchall():
            jid = str(row[0])
            emb_str = row[1]
            if emb_str:
                result[jid] = _parse_vector(emb_str)
        return result


def _parse_vector(vec_str: str) -> list[float]:
    """Parse a pgvector string '[0.1,0.2,...]' into a list of floats."""
    clean = vec_str.strip().strip("[]")
    if not clean:
        return []
    return [float(x) for x in clean.split(",")]


def _upsert_match(conn, result: MatchResult):
    """Upsert into matches table, then replace dimension_scores rows."""
    match_data = {
        "applicant_id":           result.applicant_id,
        "job_id":                 result.job_id,
        "eligibility_status":     result.eligibility_status,
        "hard_gate_cap":          result.hard_gate_cap,
        "hard_gate_failures":     json.dumps(result.hard_gate_failures),
        "hard_gate_rationale":    json.dumps(result.hard_gate_rationale),
        "weighted_structured_score": result.weighted_structured_score,
        "semantic_score":         result.semantic_score,
        "base_fit_score":         result.base_fit_score,
        "policy_modifiers":       json.dumps(result.policy_modifiers),
        "policy_adjusted_score":  result.policy_adjusted_score,
        "match_label":            result.match_label,
        "top_strengths":          json.dumps(result.top_strengths),
        "top_gaps":               json.dumps(result.top_gaps),
        "required_missing_items": json.dumps(result.required_missing_items),
        "recommended_next_step":  result.recommended_next_step,
        "confidence_level":       result.confidence_level,
        "requires_review":        result.requires_review,
        "match_tier":             result.match_tier,
        "tier_reason":            result.tier_reason,
        "distance_miles":         result.distance_miles,
        "scoring_run_id":         result.scoring_run_id,
        "scoring_run_at":         result.scoring_run_at,
        "policy_version":         result.policy_version,
    }

    with conn.cursor() as cur:
        # Upsert match row
        cur.execute("""
            INSERT INTO public.matches (
                applicant_id, job_id,
                eligibility_status, hard_gate_cap, hard_gate_failures, hard_gate_rationale,
                weighted_structured_score, semantic_score, base_fit_score,
                policy_modifiers, policy_adjusted_score,
                match_label, top_strengths, top_gaps, required_missing_items,
                recommended_next_step,
                confidence_level, requires_review,
                match_tier, tier_reason, distance_miles,
                scoring_run_id, scoring_run_at, policy_version
            ) VALUES (
                %(applicant_id)s, %(job_id)s,
                %(eligibility_status)s, %(hard_gate_cap)s,
                %(hard_gate_failures)s::jsonb, %(hard_gate_rationale)s::jsonb,
                %(weighted_structured_score)s, %(semantic_score)s, %(base_fit_score)s,
                %(policy_modifiers)s::jsonb, %(policy_adjusted_score)s,
                %(match_label)s,
                %(top_strengths)s::jsonb, %(top_gaps)s::jsonb,
                %(required_missing_items)s::jsonb,
                %(recommended_next_step)s,
                %(confidence_level)s, %(requires_review)s,
                %(match_tier)s, %(tier_reason)s, %(distance_miles)s,
                %(scoring_run_id)s::uuid, %(scoring_run_at)s::date, %(policy_version)s
            )
            ON CONFLICT (applicant_id, job_id) DO UPDATE SET
                eligibility_status     = EXCLUDED.eligibility_status,
                hard_gate_cap          = EXCLUDED.hard_gate_cap,
                hard_gate_failures     = EXCLUDED.hard_gate_failures,
                hard_gate_rationale    = EXCLUDED.hard_gate_rationale,
                weighted_structured_score = EXCLUDED.weighted_structured_score,
                semantic_score         = EXCLUDED.semantic_score,
                base_fit_score         = EXCLUDED.base_fit_score,
                policy_modifiers       = EXCLUDED.policy_modifiers,
                policy_adjusted_score  = EXCLUDED.policy_adjusted_score,
                match_label            = EXCLUDED.match_label,
                top_strengths          = EXCLUDED.top_strengths,
                top_gaps               = EXCLUDED.top_gaps,
                required_missing_items = EXCLUDED.required_missing_items,
                recommended_next_step  = EXCLUDED.recommended_next_step,
                confidence_level       = EXCLUDED.confidence_level,
                requires_review        = EXCLUDED.requires_review,
                match_tier             = EXCLUDED.match_tier,
                tier_reason            = EXCLUDED.tier_reason,
                distance_miles         = EXCLUDED.distance_miles,
                scoring_run_id         = EXCLUDED.scoring_run_id,
                scoring_run_at         = EXCLUDED.scoring_run_at,
                policy_version         = EXCLUDED.policy_version,
                updated_at             = NOW()
            RETURNING id
        """, match_data)

        match_row = cur.fetchone()
        if not match_row:
            return
        match_id = str(match_row[0])

        # Replace dimension scores (delete + insert)
        cur.execute(
            "DELETE FROM public.match_dimension_scores WHERE match_id = %s",
            (match_id,)
        )

        for dim in result.dimension_scores:
            cur.execute("""
                INSERT INTO public.match_dimension_scores
                    (match_id, dimension, weight, raw_score, weighted_score,
                     rationale, null_handling_applied, null_handling_default)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                match_id,
                dim.dimension,
                dim.weight,
                dim.raw_score,
                dim.weighted_score,
                dim.rationale,
                dim.null_handling_applied,
                dim.null_handling_default,
            ))


def _print_match(result: MatchResult, app: dict, job: dict):
    name = f"{app.get('first_name', '')} {app.get('last_name', '')}".strip() or str(app["id"])[:8]
    jtitle = (job.get("title_normalized") or job.get("title_raw") or "")[:30]
    print(
        f"  [{result.eligibility_status.upper():10s}] "
        f"score={result.policy_adjusted_score:5.1f} | "
        f"{name[:20]:20s} → {jtitle}"
    )


if __name__ == "__main__":
    sys.exit(main())
