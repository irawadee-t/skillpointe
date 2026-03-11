#!/usr/bin/env python3
"""
verify_schema.py — Phase 3 schema verification

Connects to the local Supabase Postgres (or any Postgres defined by
DATABASE_URL / SUPABASE_DB_URL) and checks that:

  1. All expected tables exist in the public schema.
  2. All expected enum types exist.
  3. Seed data rows are present (taxonomy + policy config).
  4. The active policy config is readable and contains required keys.

Usage (from repo root):
    cd apps/api && source .venv/bin/activate
    cd ../..
    python scripts/verify_schema.py

Or with an explicit URL:
    DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres \\
        python scripts/verify_schema.py

Exit code: 0 = all checks passed, 1 = at least one check failed.
"""
import os
import sys
from pathlib import Path

# Load .env from apps/api if available
env_file = Path(__file__).parent.parent / "apps" / "api" / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

# Supabase local Postgres default: port 54322, user postgres, password postgres
DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("SUPABASE_DB_URL")
    or "postgresql://postgres:postgres@localhost:54322/postgres"
)

# ------------------------------------------------------------------ #
# Expected state
# ------------------------------------------------------------------ #

EXPECTED_TABLES = [
    "user_profiles",
    "canonical_job_families",
    "canonical_career_pathways",
    "geography_regions",
    "applicants",
    "employers",
    "employer_contacts",
    "jobs",
    "applicant_documents",
    "extracted_applicant_signals",
    "extracted_job_signals",
    "matches",
    "match_dimension_scores",
    "saved_jobs",
    "import_runs",
    "import_rows",
    "audit_logs",
    "policy_configs",
    "review_queue_items",
    "chat_sessions",
    "chat_messages",
]

EXPECTED_ENUMS = [
    "eligibility_status_enum",
    "confidence_level_enum",
    "review_status_enum",
    "match_label_enum",
    "work_setting_enum",
    "document_type_enum",
    "import_status_enum",
    "review_queue_item_type_enum",
    "chat_role_enum",
]

EXPECTED_SEED_COUNTS = {
    "geography_regions": 6,
    "canonical_job_families": 15,
    "canonical_career_pathways": 15,
}

REQUIRED_POLICY_KEYS = [
    "structured_score",
    "eligibility",
    "policy_reranking",
    "null_handling",
    "feature_flags",
]


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m  {msg}")


def fail(msg: str) -> None:
    print(f"  \033[31m✗\033[0m  {msg}")


def header(msg: str) -> None:
    print(f"\n\033[1m{msg}\033[0m")


# ------------------------------------------------------------------ #
# Main verification
# ------------------------------------------------------------------ #

def run() -> int:
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
        return 1

    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cur = conn.cursor()
        print(f"Connected to: {DATABASE_URL}")
    except Exception as exc:
        print(f"ERROR: Could not connect to database.\n  {exc}")
        print("\nIs local Supabase running?  Run: supabase start")
        return 1

    failures = 0

    # 1. Tables
    header("1. Tables")
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
    """)
    existing_tables = {row[0] for row in cur.fetchall()}
    for table in EXPECTED_TABLES:
        if table in existing_tables:
            ok(table)
        else:
            fail(f"{table}  ← MISSING")
            failures += 1

    # 2. Enum types
    header("2. Enum types")
    cur.execute("""
        SELECT typname
        FROM pg_type
        WHERE typcategory = 'E'
          AND typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
    """)
    existing_enums = {row[0] for row in cur.fetchall()}
    for enum in EXPECTED_ENUMS:
        if enum in existing_enums:
            ok(enum)
        else:
            fail(f"{enum}  ← MISSING")
            failures += 1

    # 3. Seed row counts
    header("3. Seed data row counts")
    for table, min_rows in EXPECTED_SEED_COUNTS.items():
        cur.execute(f"SELECT COUNT(*) FROM public.{table}")
        count = cur.fetchone()[0]
        if count >= min_rows:
            ok(f"{table}: {count} rows (expected ≥ {min_rows})")
        else:
            fail(f"{table}: {count} rows (expected ≥ {min_rows})")
            failures += 1

    # 4. Active policy config
    header("4. Active policy config (v1)")
    cur.execute("""
        SELECT version, config
        FROM public.policy_configs
        WHERE is_active = TRUE
        LIMIT 1
    """)
    row = cur.fetchone()
    if row is None:
        fail("No active policy_config found")
        failures += 1
    else:
        version, config = row
        ok(f"Active config version: {version}")
        for key in REQUIRED_POLICY_KEYS:
            if key in config:
                ok(f"  policy key present: {key}")
            else:
                fail(f"  policy key MISSING: {key}")
                failures += 1

    # 5. pgvector extension
    header("5. pgvector extension")
    cur.execute("""
        SELECT extname FROM pg_extension WHERE extname = 'vector'
    """)
    if cur.fetchone():
        ok("pgvector (vector) extension installed")
    else:
        fail("pgvector extension NOT found — semantic scoring will not work")
        failures += 1

    # Summary
    print()
    if failures == 0:
        print("\033[32m✓ All checks passed.\033[0m\n")
        return 0
    else:
        print(f"\033[31m✗ {failures} check(s) failed.\033[0m")
        print("  Run `supabase db reset` to apply all migrations and seed data.\n")
        return 1


if __name__ == "__main__":
    sys.exit(run())
