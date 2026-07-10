"""
File-drop ingestion lane (the SFTP path).

An SFTP/secure file-drop partner deposits CSV batches; this lane parses them into
ingest rows that flow through the SAME pipeline as the partner-portal API lane.
Parsing is pure + unit-tested; the transport (SFTP poller / object-store trigger)
is deployment config, not application logic. Expected header columns:

    email, credential_name, issuer, issued_date, expires_date
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass

REQUIRED = ("email", "credential_name")
_ALIASES = {
    "credential": "credential_name",
    "credential name": "credential_name",
    "name": "credential_name",
    "e-mail": "email",
    "issued": "issued_date",
    "expires": "expires_date",
    "expiration": "expires_date",
}


@dataclass(frozen=True)
class ParsedFile:
    rows: list[dict[str, str]]
    skipped: int          # rows missing a required field
    headers: list[str]


def _norm_header(h: str) -> str:
    key = (h or "").strip().lower()
    return _ALIASES.get(key, key.replace(" ", "_"))


def parse_csv(text: str) -> ParsedFile:
    reader = csv.DictReader(io.StringIO(text or ""))
    raw_headers = reader.fieldnames or []
    headers = [_norm_header(h) for h in raw_headers]
    rows: list[dict[str, str]] = []
    skipped = 0

    for raw in reader:
        row = { _norm_header(k): (v or "").strip() for k, v in raw.items() if k is not None }
        if not all(row.get(c) for c in REQUIRED):
            skipped += 1
            continue
        rows.append({
            "email": row["email"],
            "credential_name": row["credential_name"],
            "issuer": row.get("issuer") or None,
            "issued_date": row.get("issued_date") or None,
            "expires_date": row.get("expires_date") or None,
        })
    return ParsedFile(rows=rows, skipped=skipped, headers=headers)
