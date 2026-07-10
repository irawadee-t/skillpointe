/**
 * SKILLED Pro — admin bulk credential ingestion (partner-portal lane).
 * Backend: apps/api/app/routers/ingest.py
 */
import { apiFetch } from "./client";

export interface IngestRow {
  email: string;
  credential_name: string;
  issuer?: string | null;
  issued_date?: string | null;
  expires_date?: string | null;
}

export interface IngestRequest {
  institution: string;
  rows: IngestRow[];
  dry_run: boolean;
}

export interface RowResult {
  email: string;
  credential_name: string;
  status: "ok" | "unmatched" | "error";
  action: "created" | "upgraded" | "unchanged" | null;
  applicant_name: string | null;
  canonical_name: string | null;
  verification_badge: string | null;
  needs_review: boolean;
  detail: string | null;
}

export interface IngestSummary {
  dry_run: boolean;
  institution: string;
  total: number;
  matched: number;
  created: number;
  upgraded: number;
  unchanged: number;
  unmatched: number;
  errors: number;
  import_run_id: string | null;
  results: RowResult[];
}

export function ingestCredentials(token: string, body: IngestRequest): Promise<IngestSummary> {
  return apiFetch<IngestSummary>("/admin/credentials/ingest", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Pull credential completions from the configured SIS provider (mock by default). */
export function ingestFromSis(token: string, dryRun: boolean): Promise<IngestSummary> {
  return apiFetch<IngestSummary>("/admin/credentials/ingest/sis", token, {
    method: "POST",
    body: JSON.stringify({ dry_run: dryRun }),
  });
}

/**
 * Parse a simple CSV (header row with email, credential_name, issuer,
 * issued_date, expires_date — order-independent, extra columns ignored).
 * Returns rows + any parse warnings. Minimal quote handling.
 */
export function parseCsv(text: string): { rows: IngestRow[]; error: string | null } {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  if (lines.length === 0) return { rows: [], error: "Empty input" };

  const split = (line: string) =>
    line.split(",").map((c) => c.trim().replace(/^"(.*)"$/, "$1"));

  const header = split(lines[0]).map((h) => h.toLowerCase().replace(/\s+/g, "_"));
  const hasHeader = header.includes("email") || header.includes("credential_name") || header.includes("credential");
  const cols = hasHeader
    ? header
    : ["email", "credential_name", "issuer", "issued_date", "expires_date"];
  const dataLines = hasHeader ? lines.slice(1) : lines;

  const idx = (names: string[]) => names.map((n) => cols.indexOf(n)).find((i) => i >= 0) ?? -1;
  const iEmail = idx(["email"]);
  const iName = idx(["credential_name", "credential", "name"]);
  const iIssuer = idx(["issuer"]);
  const iIssued = idx(["issued_date", "issued"]);
  const iExpires = idx(["expires_date", "expires"]);

  if (iEmail < 0 || iName < 0) {
    return { rows: [], error: "CSV must include 'email' and 'credential_name' columns." };
  }

  const rows: IngestRow[] = [];
  for (const line of dataLines) {
    const c = split(line);
    const email = c[iEmail] ?? "";
    const name = c[iName] ?? "";
    if (!email && !name) continue;
    rows.push({
      email,
      credential_name: name,
      issuer: iIssuer >= 0 ? c[iIssuer] || null : null,
      issued_date: iIssued >= 0 ? c[iIssued] || null : null,
      expires_date: iExpires >= 0 ? c[iExpires] || null : null,
    });
  }
  return { rows, error: rows.length === 0 ? "No data rows found." : null };
}
