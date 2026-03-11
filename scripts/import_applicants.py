#!/usr/bin/env python3
"""
import_applicants.py — Phase 4.1: Applicant import pipeline

Reads a CSV or XLSX file of applicants, maps columns to the applicants
schema, preserves all raw data, and writes to Supabase Postgres.

Usage:
    # Inspect file headers without importing
    python scripts/import_applicants.py --file data/applicants.xlsx --inspect-headers

    # Dry run: show what would be imported without writing
    python scripts/import_applicants.py --file data/applicants.xlsx --dry-run

    # Live import
    python scripts/import_applicants.py --file data/applicants.xlsx

    # With verbose per-row output
    python scripts/import_applicants.py --file data/applicants.xlsx --verbose

Options:
    --file            Path to CSV or XLSX file (required)
    --inspect-headers Show column mapping and exit (no import)
    --dry-run         Map and validate all rows but do not write to DB
    --verbose         Print per-row results during import
    --limit N         Import only the first N rows (useful for testing)

Requirements:
    pip install pandas openpyxl python-dateutil psycopg2-binary python-dotenv

See BUILD_PLAN.md §4 Step 4.1.
"""
import argparse
import sys
from pathlib import Path

# Allow importing from packages/ without pip-installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "packages"))

from etl.loader import load_file, inspect_headers
from etl.models import ImportResult, ImportRowResult
from etl.reporting import print_summary, print_row_verbose
from etl import applicant_mapper


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import applicants from CSV/XLSX into SkillPointe Match DB"
    )
    parser.add_argument("--file", required=True, help="Path to CSV or XLSX file")
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

    # ---- Inspect mode ----
    if args.inspect_headers:
        inspect_headers(file_path, applicant_mapper.COLUMN_MAP)
        return 0

    # ---- Load file ----
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

    # Identify unmapped columns (for summary reporting)
    unmapped_cols = [
        raw
        for raw, norm in zip(raw_headers, norm_headers)
        if norm not in applicant_mapper.COLUMN_MAP
    ]

    result = ImportResult(
        import_type="applicants",
        source_file=str(file_path),
        dry_run=args.dry_run,
        unmapped_columns=unmapped_cols,
    )

    # ---- Set up DB (skip in dry-run) ----
    conn = None
    if not args.dry_run:
        try:
            from etl.db import get_connection, create_import_run, complete_import_run
            from etl.db import insert_applicant, insert_import_row
            conn = get_connection()
            result.run_id = create_import_run(
                conn,
                import_type="applicants",
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

    # ---- Process rows ----
    print(f"\nProcessing {len(rows)} rows from {file_path.name} ...")
    if args.dry_run:
        print("(DRY RUN — no data will be written)\n")

    for i, raw_row in enumerate(rows, start=1):
        # Map row
        applicant, map_warnings = applicant_mapper.map_row(raw_row, row_number=i)
        # Validate
        validation_warnings = applicant_mapper.validate(applicant, row_number=i)
        all_warnings = map_warnings + validation_warnings

        warning_msg = "; ".join(all_warnings) if all_warnings else None

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
            applicant_id = insert_applicant(conn, applicant, result.run_id)

            insert_import_row(
                conn,
                run_id=result.run_id,
                row_number=i,
                raw_data=raw_row,
                status="warning" if all_warnings else "success",
                warning_message=warning_msg,
                entity_id=applicant_id,
                entity_type="applicant",
            )
            conn.commit()

            row_result = ImportRowResult(
                row_number=i,
                status="warning" if all_warnings else "success",
                raw_data=raw_row,
                warning_message=warning_msg,
                entity_id=applicant_id,
                entity_type="applicant",
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

    # ---- Finalize ----
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
