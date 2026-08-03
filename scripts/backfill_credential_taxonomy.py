#!/usr/bin/env python3
"""
backfill_credential_taxonomy.py — normalize existing credential data against
the canonical taxonomy (apps/api/app/skilled_pro/taxonomy.py).

What it does (idempotent, additive — raw text is NEVER modified):

  1. credentials rows
     - canonical_code IS NULL             → re-run the normalizer on raw_name;
       fill canonical fields + definition_id when confident, else flag
       needs_review and enqueue ONE pending taxonomy_mismatch review item.
     - legacy/broken canonical_code (not a current slug) → re-normalize and
       rewrite to the current slug when confident.
     - valid slug but missing definition_id → link the definition row.
     - Admin-fixed rows (valid slug + definition) are left untouched.

  2. jobs.required_credentials → jobs.required_credentials_canonical
     [{raw, slug, name, confidence, confident}] per entry — consumed by the
     recompute data-prep layer so both sides of the credential gate meet on
     canonical names instead of raw-string luck.

Usage:
    cd apps/api && source .venv/bin/activate && cd ../..
    python scripts/backfill_credential_taxonomy.py [--dry-run] [--verbose]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))
sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))

from etl.db import get_connection  # noqa: E402

from app.skilled_pro import taxonomy  # noqa: E402


def _definition_ids(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT canonical_code, id FROM public.credential_definitions WHERE active")
        return {code: str(def_id) for code, def_id in cur.fetchall()}


def backfill_credentials(conn, *, dry_run: bool, verbose: bool) -> dict:
    def_ids = _definition_ids(conn)
    stats = {
        "total": 0, "already_canonical": 0, "filled": 0, "relinked": 0,
        "rewritten_legacy": 0, "flagged_review": 0, "unmatched": 0,
    }
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, raw_name, canonical_code, canonical_name, credential_type, "
            "issuer, definition_id, needs_review FROM public.credentials"
        )
        rows = cur.fetchall()

    for (cred_id, raw_name, code, _cname, _ctype, _issuer, definition_id, needs_review) in rows:
        stats["total"] += 1
        current = taxonomy.get_by_slug(code) if code else None

        if current is not None and definition_id is not None:
            stats["already_canonical"] += 1
            continue

        if current is not None and definition_id is None:
            # Valid slug, just link the definition row.
            stats["relinked"] += 1
            if not dry_run:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE public.credentials SET definition_id = %s::uuid WHERE id = %s",
                        (def_ids.get(current.slug), cred_id),
                    )
            continue

        # No canonical link, or a legacy/broken code — re-run the normalizer.
        norm = taxonomy.normalize(raw_name or "")
        if norm.is_confident and norm.canonical is not None:
            c = norm.canonical
            key = "rewritten_legacy" if code else "filled"
            stats[key] += 1
            if verbose:
                print(f"  {raw_name!r}: {code or '—'} -> {c.slug} ({norm.method} {norm.confidence})")
            if not dry_run:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE public.credentials
                           SET canonical_code = %s, canonical_name = %s,
                               credential_type = COALESCE(credential_type, %s),
                               issuer = COALESCE(issuer, %s),
                               normalization_confidence = %s,
                               definition_id = %s::uuid,
                               updated_at = now()
                         WHERE id = %s
                        """,
                        (c.slug, c.name, c.type.value, c.issuer,
                         norm.confidence, def_ids.get(c.slug), cred_id),
                    )
        else:
            stats["unmatched"] += 1
            if verbose:
                cand = norm.canonical.slug if norm.canonical else None
                print(f"  {raw_name!r}: no confident match (candidate={cand}, conf={norm.confidence})")
            if not dry_run:
                with conn.cursor() as cur:
                    if not needs_review:
                        cur.execute(
                            "UPDATE public.credentials SET needs_review = true, updated_at = now() "
                            "WHERE id = %s", (cred_id,),
                        )
                    # Enqueue once per pending credential.
                    cur.execute(
                        "SELECT 1 FROM public.review_queue_items "
                        "WHERE entity_type = 'credential' AND entity_id = %s::uuid "
                        "AND item_type = 'taxonomy_mismatch' AND status = 'pending'",
                        (cred_id,),
                    )
                    if cur.fetchone() is None:
                        stats["flagged_review"] += 1
                        desc = (
                            f"Credential '{raw_name}' has no confident canonical match "
                            f"(best={norm.canonical.slug if norm.canonical else None}, "
                            f"confidence={norm.confidence:.2f})."
                        )
                        cur.execute(
                            """
                            INSERT INTO public.review_queue_items
                              (item_type, entity_type, entity_id, description, flags,
                               confidence_level, priority)
                            VALUES ('taxonomy_mismatch', 'credential', %s::uuid, %s,
                                    %s::jsonb, 'low', 5)
                            """,
                            (cred_id, desc, json.dumps([{
                                "flag_type": "taxonomy_normalization",
                                "detail": {
                                    "raw_name": raw_name,
                                    "method": norm.method,
                                    "confidence": norm.confidence,
                                    "candidate": norm.canonical.slug if norm.canonical else None,
                                },
                            }])),
                        )
    return stats


def backfill_jobs(conn, *, dry_run: bool, verbose: bool) -> dict:
    stats = {"jobs_with_reqs": 0, "req_total": 0, "req_matched": 0, "req_unmatched": 0}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, required_credentials FROM public.jobs "
            "WHERE required_credentials IS NOT NULL AND array_length(required_credentials, 1) > 0"
        )
        rows = cur.fetchall()

    for job_id, reqs in rows:
        stats["jobs_with_reqs"] += 1
        canonical = []
        for raw in reqs:
            stats["req_total"] += 1
            norm = taxonomy.normalize(raw or "")
            confident = bool(norm.is_confident and norm.canonical)
            stats["req_matched" if confident else "req_unmatched"] += 1
            canonical.append({
                "raw": raw,
                "slug": norm.canonical.slug if confident else None,
                "name": norm.canonical.name if confident else None,
                "confidence": norm.confidence,
                "confident": confident,
            })
            if verbose:
                tgt = canonical[-1]["slug"] or "—"
                print(f"  job {job_id}: {raw!r} -> {tgt}")
        if not dry_run:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.jobs SET required_credentials_canonical = %s::jsonb "
                    "WHERE id = %s",
                    (json.dumps(canonical), job_id),
                )
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill canonical credential taxonomy links")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    conn = get_connection()
    try:
        cred_stats = backfill_credentials(conn, dry_run=args.dry_run, verbose=args.verbose)
        job_stats = backfill_jobs(conn, dry_run=args.dry_run, verbose=args.verbose)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()

    print("\n=== credentials ===")
    for k, v in cred_stats.items():
        print(f"  {k:20} {v}")
    linked = (cred_stats["already_canonical"] + cred_stats["filled"]
              + cred_stats["relinked"] + cred_stats["rewritten_legacy"])
    if cred_stats["total"]:
        print(f"  hit rate            {linked}/{cred_stats['total']} "
              f"({100.0 * linked / cred_stats['total']:.1f}%)")
    print("=== jobs.required_credentials ===")
    for k, v in job_stats.items():
        print(f"  {k:20} {v}")
    if job_stats["req_total"]:
        print(f"  hit rate            {job_stats['req_matched']}/{job_stats['req_total']} "
              f"({100.0 * job_stats['req_matched'] / job_stats['req_total']:.1f}%)")
    if args.dry_run:
        print("\n(dry run — nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
