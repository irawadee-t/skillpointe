#!/usr/bin/env python3
"""
import_jobs.py — Phase 4.2: Job import pipeline

Reads a CSV or XLSX file of job postings, maps columns to the jobs schema,
preserves all raw data, creates employer records as needed, and writes
to Supabase Postgres.

Usage:
    # Inspect file headers without importing
    python scripts/import_jobs.py --file data/jobs.xlsx --inspect-headers

    # Dry run: show what would be imported without writing
    python scripts/import_jobs.py --file data/jobs.xlsx --dry-run

    # Live import
    python scripts/import_jobs.py --file data/jobs.xlsx

    # All jobs belong to one employer (useful if no "company" column in file)
    python scripts/import_jobs.py --file data/jobs.xlsx --employer-name "Acme Corp"

    # Verbose per-row output
    python scripts/import_jobs.py --file data/jobs.xlsx --verbose

Options:
    --file            Path to CSV or XLSX file (required)
    --employer-name   Default employer name if not in file columns
    --inspect-headers Show column mapping and exit (no import)
    --dry-run         Map and validate all rows but do not write to DB
    --verbose         Print per-row results during import
    --limit N         Import only the first N rows

Requirements:
    pip install pandas openpyxl python-dateutil psycopg2-binary python-dotenv

See BUILD_PLAN.md §4 Step 4.2.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))

from etl.loader import load_file, inspect_headers
from etl.models import ImportResult, ImportRowResult
from etl.reporting import print_summary, print_row_verbose
from etl import job_mapper


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import jobs from CSV/XLSX into SkillPointe Match DB"
    )
    parser.add_argument("--file", required=True, help="Path to CSV or XLSX file")
    parser.add_argument(
        "--employer-name",
        default=None,
        help="Default employer name for all rows (overridden by file column if present)",
    )
    parser.add_argument(
        "--inspect-headers",
        action="store_true",
        help="Show column mapping and exit without importing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Map and validate rows but do not write to DB",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-row results",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Import only the first N rows",
    )
    args = parser.parse_args()

    file_path = Path(args.file)

    if args.inspect_headers:
        inspect_headers(file_path, job_mapper.COLUMN_MAP)
        return 0

    try:
        rows, raw_headers, norm_headers = load_file(file_path)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1
    except Exception as e:
        print(f"ERROR loading file: {e}")
        return 1

    if args.limit:
        rows = rows[: args.limit]

    unmapped_cols = [
        raw
        for raw, norm in zip(raw_headers, norm_headers)
        if norm not in job_mapper.COLUMN_MAP
    ]

    result = ImportResult(
        import_type="jobs",
        source_file=str(file_path),
        dry_run=args.dry_run,
        unmapped_columns=unmapped_cols,
    )

    conn = None
    if not args.dry_run:
        try:
            from etl.db import (
                get_connection,
                create_import_run,
                complete_import_run,
                find_or_create_employer,
                insert_job,
                insert_import_row,
            )
            conn = get_connection()
            result.run_id = create_import_run(
                conn,
                import_type="jobs",
                source_file=file_path.name,
                row_count=len(rows),
            )
            conn.commit()
        except ImportError as e:
            print(f"ERROR: {e}")
            return 1
        except Exception as e:
            print(f"ERROR connecting to database: {e}")
            print("Is local Supabase running?  Run: supabase start")
            return 1

    print(f"\nProcessing {len(rows)} rows from {file_path.name} ...")
    if args.dry_run:
        print("(DRY RUN — no data will be written)\n")

    for i, raw_row in enumerate(rows, start=1):
        job, map_warnings = job_mapper.map_row(
            raw_row,
            row_number=i,
            default_employer_name=args.employer_name,
        )
        is_valid, validation_issues = job_mapper.validate(job, row_number=i)
        all_warnings = map_warnings + validation_issues
        warning_msg = "; ".join(all_warnings) if all_warnings else None

        if not is_valid:
            # Hard error — cannot insert without employer
            error_msg = "; ".join(validation_issues)
            row_result = ImportRowResult(
                row_number=i,
                status="error",
                raw_data=raw_row,
                error_message=error_msg,
            )
            result.add_row(row_result)
            if args.verbose:
                print_row_verbose(row_result)

            if not args.dry_run and conn:
                insert_import_row(
                    conn,
                    run_id=result.run_id,
                    row_number=i,
                    raw_data=raw_row,
                    status="error",
                    error_message=error_msg[:500],
                )
                conn.commit()
            continue

        if args.dry_run:
            status = "warning" if all_warnings else "success"
            row_result = ImportRowResult(
                row_number=i,
                status=status,
                raw_data=raw_row,
                warning_message=warning_msg,
            )
            result.add_row(row_result)
            if args.verbose:
                print_row_verbose(row_result)
            continue

        # Live insert
        try:
            employer_id = find_or_create_employer(conn, job.employer_name, result.run_id)
            job_id = insert_job(conn, job, employer_id, result.run_id)

            insert_import_row(
                conn,
                run_id=result.run_id,
                row_number=i,
                raw_data=raw_row,
                status="warning" if all_warnings else "success",
                warning_message=warning_msg,
                entity_id=job_id,
                entity_type="job",
            )
            conn.commit()

            row_result = ImportRowResult(
                row_number=i,
                status="warning" if all_warnings else "success",
                raw_data=raw_row,
                warning_message=warning_msg,
                entity_id=job_id,
                entity_type="job",
            )
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            error_msg = str(e)
            insert_import_row(
                conn,
                run_id=result.run_id,
                row_number=i,
                raw_data=raw_row,
                status="error",
                error_message=error_msg[:500],
            )
            conn.commit()
            row_result = ImportRowResult(
                row_number=i,
                status="error",
                raw_data=raw_row,
                error_message=error_msg,
            )

        result.add_row(row_result)
        if args.verbose:
            print_row_verbose(row_result)

    if not args.dry_run and conn:
        from etl.db import complete_import_run
        status = "complete" if result.error_count == 0 else "partial"
        errors = [r for r in result.row_results if r.status == "error"]
        error_summary = (
            {"sample_errors": [r.error_message for r in errors[:5]]}
            if errors
            else None
        )
        complete_import_run(
            conn,
            result.run_id,
            success_count=result.success_count + result.warning_count,
            error_count=result.error_count,
            warning_count=result.warning_count,
            status=status,
            error_summary=error_summary,
        )
        conn.commit()
        conn.close()

    print_summary(result)
    return 0 if result.error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
