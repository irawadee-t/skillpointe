#!/usr/bin/env python3
"""
run_extraction.py — Phase 7: LLM extraction pipeline.

Extracts structured signals from applicant profiles and job postings,
generates embeddings for semantic scoring, and flags low-confidence
items for admin review.

Prerequisites:
  1. OPENAI_API_KEY set in apps/api/.env or environment
  2. Local Supabase running: supabase start
  3. Data imported: import_applicants.py + import_jobs.py

Usage:
  # Full extraction — all applicants + all jobs
  python scripts/run_extraction.py

  # Applicants only
  python scripts/run_extraction.py --applicants-only

  # Jobs only
  python scripts/run_extraction.py --jobs-only

  # Single applicant or job
  python scripts/run_extraction.py --applicant-id <uuid>
  python scripts/run_extraction.py --job-id <uuid>

  # Skip already-extracted entities
  python scripts/run_extraction.py --skip-existing

  # Force re-extraction of everything
  python scripts/run_extraction.py --force

  # Skip embeddings (extraction only)
  python scripts/run_extraction.py --no-embeddings

  # Use LLM verifier for borderline cases
  python scripts/run_extraction.py --verify

  # Dry-run: extract but don't write to DB
  python scripts/run_extraction.py --dry-run

  # Limit to first N
  python scripts/run_extraction.py --limit 10

After extraction, recompute matches:
  python scripts/recompute_matches.py
"""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))

from extraction.client import get_openai_client
from extraction.applicant_extractor import extract_applicant_signals
from extraction.job_extractor import extract_job_signals
from extraction.verifier import verify_extraction
from extraction.embeddings import build_applicant_text, build_job_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LLM extraction pipeline")
    parser.add_argument("--applicants-only", action="store_true")
    parser.add_argument("--jobs-only", action="store_true")
    parser.add_argument("--applicant-id", default=None)
    parser.add_argument("--job-id", default=None)
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip entities that already have extraction results")
    parser.add_argument("--force", action="store_true",
                        help="Re-extract even if results exist")
    parser.add_argument("--no-embeddings", action="store_true",
                        help="Skip embedding generation")
    parser.add_argument("--verify", action="store_true",
                        help="Run LLM verifier on extractions")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", default=None,
                        help="Override extraction model (default: gpt-4o-mini)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    # Load env
    env_file = Path(__file__).parent.parent / "apps" / "api" / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set in environment or apps/api/.env")
        print("Add it to apps/api/.env:  OPENAI_API_KEY=sk-...")
        return 1

    model = args.model or os.environ.get("LLM_EXTRACTION_MODEL", "gpt-4o-mini")
    generate_emb = not args.no_embeddings

    from etl.db import get_connection
    try:
        conn = get_connection()
    except Exception as e:
        print(f"ERROR connecting to DB: {e}")
        return 1

    client = get_openai_client(api_key)
    print(f"Extraction model: {model}")
    print(f"Embeddings: {'enabled' if generate_emb else 'disabled'}")
    if args.dry_run:
        print("(DRY RUN — no data will be written)\n")

    counters = {"app_extracted": 0, "app_skipped": 0, "app_error": 0,
                "job_extracted": 0, "job_skipped": 0, "job_error": 0,
                "review_items": 0}

    # ------- Applicant extraction -------
    if not args.jobs_only:
        applicants = _fetch_applicants(conn, args.applicant_id, args.limit)
        existing_app_ids = _fetch_existing_extraction_ids(conn, "applicant") if args.skip_existing else set()
        print(f"\nApplicants to process: {len(applicants)}")

        for i, app in enumerate(applicants, 1):
            app_id = str(app["id"])
            name = f"{app.get('first_name', '')} {app.get('last_name', '')}".strip() or app_id[:8]

            if args.skip_existing and app_id in existing_app_ids and not args.force:
                counters["app_skipped"] += 1
                if args.verbose:
                    print(f"  [{i}/{len(applicants)}] SKIP {name} (already extracted)")
                continue

            try:
                signals = extract_applicant_signals(
                    client, model, app,
                    generate_emb=generate_emb,
                )
                if args.verbose:
                    n_skills = len(signals.skills)
                    n_certs = len(signals.certifications)
                    print(f"  [{i}/{len(applicants)}] {name}: "
                          f"{n_skills} skills, {n_certs} certs, "
                          f"conf={signals.overall_confidence}")

                verification = None
                if args.verify:
                    source = build_applicant_text(app)
                    verification = verify_extraction(
                        "applicant", app_id, source, signals.raw_llm_output,
                        client=client, model=model, use_llm=True,
                    )

                if not args.dry_run:
                    _upsert_applicant_signals(conn, signals)
                    if verification and verification.review_queue_items:
                        for item in verification.review_queue_items:
                            _insert_review_queue_item(conn, item, signals.applicant_id)
                            counters["review_items"] += 1
                    elif signals.requires_review:
                        _insert_review_queue_item(conn, {
                            "item_type": "low_confidence_extraction",
                            "entity_type": "extracted_applicant_signals",
                            "description": "low-confidence applicant extraction",
                            "confidence_level": signals.confidence_enum,
                            "priority": 5,
                        }, app_id)
                        counters["review_items"] += 1
                    conn.commit()

                counters["app_extracted"] += 1

            except Exception as e:
                counters["app_error"] += 1
                print(f"  [{i}/{len(applicants)}] ERROR {name}: {e}")
                conn.rollback()

    # ------- Job extraction -------
    if not args.applicants_only:
        jobs = _fetch_jobs(conn, args.job_id, args.limit)
        existing_job_ids = _fetch_existing_extraction_ids(conn, "job") if args.skip_existing else set()
        print(f"\nJobs to process: {len(jobs)}")

        for i, job in enumerate(jobs, 1):
            job_id = str(job["id"])
            title = (job.get("title_raw") or job.get("title_normalized") or "")[:40]

            if args.skip_existing and job_id in existing_job_ids and not args.force:
                counters["job_skipped"] += 1
                if args.verbose:
                    print(f"  [{i}/{len(jobs)}] SKIP {title} (already extracted)")
                continue

            try:
                signals = extract_job_signals(
                    client, model, job,
                    generate_emb=generate_emb,
                )
                if args.verbose:
                    n_req = len(signals.required_skills)
                    n_creds = len(signals.required_credentials)
                    print(f"  [{i}/{len(jobs)}] {title}: "
                          f"{n_req} req skills, {n_creds} req creds, "
                          f"conf={signals.overall_confidence}")

                verification = None
                if args.verify:
                    source = build_job_text(job)
                    verification = verify_extraction(
                        "job", job_id, source, signals.raw_llm_output,
                        client=client, model=model, use_llm=True,
                    )

                if not args.dry_run:
                    _upsert_job_signals(conn, signals)
                    if verification and verification.review_queue_items:
                        for item in verification.review_queue_items:
                            _insert_review_queue_item(conn, item, signals.job_id)
                            counters["review_items"] += 1
                    elif signals.requires_review:
                        _insert_review_queue_item(conn, {
                            "item_type": "low_confidence_extraction",
                            "entity_type": "extracted_job_signals",
                            "description": "low-confidence job extraction",
                            "confidence_level": signals.confidence_enum,
                            "priority": 5,
                        }, job_id)
                        counters["review_items"] += 1
                    conn.commit()

                counters["job_extracted"] += 1

            except Exception as e:
                counters["job_error"] += 1
                print(f"  [{i}/{len(jobs)}] ERROR {title}: {e}")
                conn.rollback()

    conn.close()

    # Summary
    print()
    print("=" * 60)
    print(f"  Extraction summary {'[DRY RUN]' if args.dry_run else ''}")
    print("=" * 60)
    print(f"  Applicants extracted: {counters['app_extracted']}")
    print(f"  Applicants skipped:   {counters['app_skipped']}")
    print(f"  Applicant errors:     {counters['app_error']}")
    print(f"  Jobs extracted:       {counters['job_extracted']}")
    print(f"  Jobs skipped:         {counters['job_skipped']}")
    print(f"  Job errors:           {counters['job_error']}")
    print(f"  Review queue items:   {counters['review_items']}")
    print()

    total_errors = counters["app_error"] + counters["job_error"]
    return 0 if total_errors == 0 else 1


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _fetch_applicants(conn, applicant_id=None, limit=None) -> list[dict]:
    where = "WHERE 1=1"
    params = []
    if applicant_id:
        where += " AND a.id = %s"
        params.append(applicant_id)
    lim = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT a.id, a.first_name, a.last_name,
               a.program_name_raw, a.bio_raw, a.experience_raw,
               a.career_goals_raw
        FROM public.applicants a
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
        SELECT j.id, j.title_raw, j.title_normalized,
               j.description_raw, j.requirements_raw,
               j.preferred_qualifications_raw
        FROM public.jobs j
        {where}
        ORDER BY j.created_at
        {lim}
    """
    with conn.cursor() as cur:
        cur.execute(sql, params or None)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _fetch_existing_extraction_ids(conn, entity_type: str) -> set[str]:
    """Get IDs that already have extraction results."""
    if entity_type == "applicant":
        sql = "SELECT DISTINCT applicant_id FROM public.extracted_applicant_signals"
    else:
        sql = "SELECT DISTINCT job_id FROM public.extracted_job_signals"
    with conn.cursor() as cur:
        cur.execute(sql)
        return {str(r[0]) for r in cur.fetchall()}


def _upsert_applicant_signals(conn, signals):
    """Insert or replace extraction signals for an applicant."""
    embedding_str = _format_vector(signals.embedding) if signals.embedding else None

    with conn.cursor() as cur:
        # Delete previous extraction for this applicant (keep latest only)
        cur.execute(
            "DELETE FROM public.extracted_applicant_signals WHERE applicant_id = %s",
            (signals.applicant_id,)
        )
        cur.execute("""
            INSERT INTO public.extracted_applicant_signals (
                applicant_id,
                skills_extracted, certifications_extracted,
                desired_job_families, work_style_signals,
                experience_signals, readiness_signals,
                intent_signals,
                embedding,
                llm_model, prompt_version, raw_llm_output,
                confidence_level, requires_review, review_status
            ) VALUES (
                %s,
                %s::jsonb, %s::jsonb,
                %s::jsonb, %s::jsonb,
                %s::jsonb, %s::jsonb,
                %s::jsonb,
                %s,
                %s, %s, %s::jsonb,
                %s, %s, 'pending'
            )
        """, (
            signals.applicant_id,
            json.dumps(signals.skills),
            json.dumps(signals.certifications),
            json.dumps(signals.desired_job_families),
            json.dumps(signals.work_style_signals),
            json.dumps(signals.experience_signals),
            json.dumps(signals.readiness_signals),
            json.dumps(signals.intent_signals),
            embedding_str,
            signals.llm_model,
            signals.prompt_version,
            json.dumps(signals.raw_llm_output),
            signals.confidence_enum,
            signals.requires_review,
        ))


def _upsert_job_signals(conn, signals):
    """Insert or replace extraction signals for a job."""
    embedding_str = _format_vector(signals.embedding) if signals.embedding else None

    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM public.extracted_job_signals WHERE job_id = %s",
            (signals.job_id,)
        )
        cur.execute("""
            INSERT INTO public.extracted_job_signals (
                job_id,
                required_skills, preferred_skills,
                required_credentials, preferred_credentials,
                job_family_signals, experience_signals,
                work_style_signals, physical_requirement_signals,
                embedding,
                llm_model, prompt_version, raw_llm_output,
                confidence_level, requires_review, review_status
            ) VALUES (
                %s,
                %s::jsonb, %s::jsonb,
                %s::jsonb, %s::jsonb,
                %s::jsonb, %s::jsonb,
                %s::jsonb, %s::jsonb,
                %s,
                %s, %s, %s::jsonb,
                %s, %s, 'pending'
            )
        """, (
            signals.job_id,
            json.dumps(signals.required_skills),
            json.dumps(signals.preferred_skills),
            json.dumps(signals.required_credentials),
            json.dumps(signals.preferred_credentials),
            json.dumps(signals.job_family_signals),
            json.dumps(signals.experience_level if isinstance(signals.experience_level, list)
                       else [signals.experience_level] if signals.experience_level else []),
            json.dumps(signals.work_style_signals),
            json.dumps(signals.physical_requirements),
            embedding_str,
            signals.llm_model,
            signals.prompt_version,
            json.dumps(signals.raw_llm_output),
            signals.confidence_enum,
            signals.requires_review,
        ))


def _insert_review_queue_item(conn, item: dict, entity_id: str):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO public.review_queue_items
                (item_type, entity_type, entity_id, description,
                 flags, confidence_level, priority)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
        """, (
            item.get("item_type", "low_confidence_extraction"),
            item.get("entity_type", "extracted_applicant_signals"),
            entity_id,
            item.get("description", "flagged for review"),
            item.get("flags", "[]"),
            item.get("confidence_level", "low"),
            item.get("priority", 5),
        ))


def _format_vector(embedding: list[float]) -> str:
    """Format embedding list as pgvector string literal."""
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"


if __name__ == "__main__":
    sys.exit(main())
