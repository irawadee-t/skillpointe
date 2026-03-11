"""
loader.py — file loading helpers for CSV and XLSX files.

Reads a file and returns:
  - A list of dicts, one per row, with normalized header keys.
  - The original (raw) header list for inspection / reporting.

Header normalisation applied:
  - strip surrounding whitespace
  - lowercase
  - replace spaces and hyphens with underscores
  - remove leading/trailing underscores
  - collapse multiple underscores to one
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _normalize_header(h: str) -> str:
    h = str(h).strip().lower()
    # Replace all separator-like characters with underscore
    # Handles: spaces, hyphens, slashes, colons, question marks,
    # parentheses, ampersands — all common in real SkillPointe headers
    h = re.sub(r"[\s\-/\\():?&'\"]+", "_", h)
    h = re.sub(r"_+", "_", h)
    h = h.strip("_")
    return h or "unnamed"


def load_file(path: str | Path) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """
    Load a CSV or XLSX file.

    Returns:
        rows        — list of dicts keyed by *normalized* header names
        raw_headers — original header strings as they appear in the file
        norm_headers — normalized header strings
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls", ".xlsm"):
        return _load_excel(path)
    elif suffix in (".csv", ".tsv"):
        return _load_csv(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}  (expected .csv / .xlsx)")


def _load_csv(path: Path) -> tuple[list[dict], list[str], list[str]]:
    import csv

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw_headers = list(reader.fieldnames or [])
        norm_headers = [_normalize_header(h) for h in raw_headers]
        header_map = dict(zip(raw_headers, norm_headers))
        rows = []
        for row in reader:
            norm_row = {header_map[k]: v for k, v in row.items() if k is not None}
            rows.append(norm_row)
    return rows, raw_headers, norm_headers


def _load_excel(path: Path) -> tuple[list[dict], list[str], list[str]]:
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError(
            "pandas and openpyxl are required for XLSX support.\n"
            "Run: pip install pandas openpyxl"
        ) from e

    df = pd.read_excel(path, dtype=str, keep_default_na=False)
    raw_headers = list(df.columns)
    norm_headers = [_normalize_header(h) for h in raw_headers]
    df.columns = norm_headers  # type: ignore[assignment]

    # Replace pandas NA / empty strings with None
    df = df.where(df != "", other=None)  # type: ignore[arg-type]

    rows = df.to_dict(orient="records")
    return rows, raw_headers, norm_headers  # type: ignore[return-value]


def inspect_headers(
    path: str | Path,
    column_map: dict[str, str],
) -> None:
    """
    Print a summary of file headers and how they would be mapped.
    Does not load all rows — reads just enough to get headers.
    """
    path = Path(path)
    rows, raw_headers, norm_headers = load_file(path)

    print(f"\nFile:    {path.name}")
    print(f"Rows:    {len(rows)}")
    print(f"Columns: {len(raw_headers)}\n")

    mapped = []
    unmapped = []
    for raw, norm in zip(raw_headers, norm_headers):
        target = column_map.get(norm)
        if target:
            mapped.append((raw, norm, target))
        else:
            unmapped.append((raw, norm))

    print("Mapped columns:")
    for raw, norm, target in mapped:
        special = " (special)" if target.startswith("_") else ""
        print(f"  {raw!r:40s} → {target}{special}")

    if unmapped:
        print(f"\nUnmapped columns (stored in raw_data only):")
        for raw, norm in unmapped:
            print(f"  {raw!r:40s}  [norm key: {norm!r}]")
    else:
        print("\nAll columns are mapped.")
    print()
