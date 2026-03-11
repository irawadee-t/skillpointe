"""
reporting.py — console output helpers for import results.
"""
from __future__ import annotations

from .models import ImportResult, ImportRowResult


def print_summary(result: ImportResult) -> None:
    """Print a formatted summary of an import run."""
    mode = "[DRY RUN — no data written]" if result.dry_run else ""
    print(f"\n{'='*60}")
    print(f"  Import summary: {result.import_type.upper()}  {mode}")
    print(f"{'='*60}")
    print(f"  File:           {result.source_file}")
    if result.run_id:
        print(f"  Run ID:         {result.run_id}")
    print(f"  Total rows:     {result.total_rows}")
    print(f"  Inserted/updated: {result.success_count}")
    print(f"  Warnings:       {result.warning_count}")
    print(f"  Errors:         {result.error_count}")
    print(f"  Skipped:        {result.skipped_count}")
    print(f"{'='*60}")

    if result.unmapped_columns:
        print(f"\n  Unmapped columns (stored in raw_data only):")
        for col in sorted(result.unmapped_columns):
            print(f"    • {col}")

    errors = [r for r in result.row_results if r.status == "error"]
    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for r in errors[:20]:
            print(f"    Row {r.row_number}: {r.error_message}")
        if len(errors) > 20:
            print(f"    ... and {len(errors) - 20} more")

    warnings = [r for r in result.row_results if r.status == "warning"]
    if warnings:
        print(f"\n  Warnings ({len(warnings)}):")
        for r in warnings[:20]:
            print(f"    Row {r.row_number}: {r.warning_message}")
        if len(warnings) > 20:
            print(f"    ... and {len(warnings) - 20} more")

    if not result.dry_run and result.run_id:
        print(f"\n  Inspect import rows in Supabase Studio:")
        print(f"    http://localhost:54323")
        print(f"    SELECT * FROM import_rows WHERE import_run_id = '{result.run_id}';")

    print()


def print_row_verbose(row_result: ImportRowResult) -> None:
    """Print a single row result (for --verbose mode)."""
    icon = {"success": "✓", "warning": "⚠", "error": "✗", "skipped": "–"}.get(
        row_result.status, "?"
    )
    msg = row_result.error_message or row_result.warning_message or ""
    entity = f" → {row_result.entity_type}:{row_result.entity_id}" if row_result.entity_id else ""
    print(f"  {icon} Row {row_result.row_number:>4}  {row_result.status:<8}{entity}  {msg}")
