"use client";

import { useState } from "react";
import {
  Upload,
  FileText,
  Eye,
  CheckCircle2,
  Loader2,
  AlertTriangle,
  XCircle,
  ArrowUpCircle,
  CircleDashed,
  X,
} from "lucide-react";

import { Database } from "lucide-react";

import {
  IngestRow,
  IngestSummary,
  ingestCredentials,
  ingestFromSis,
  parseCsv,
} from "@/lib/api/ingest";
import { PageHeader, MonoLabel, MetricCard, Breadcrumb } from "@/components/ui";
import { cn } from "@/lib/utils";

const SAMPLE = `email,credential_name,issuer,issued_date,expires_date
applicant@test.local,EPA 608,EPA,2025-03-01,
applicant@test.local,Forklift Operator,OSHA,2025-05-12,2028-05-12
nobody@example.com,AWS Certified Welder,American Welding Society,2024-09-01,`;

export function IngestClient({ token }: { token: string }) {
  const [institution, setInstitution] = useState("");
  const [csv, setCsv] = useState("");
  const [rows, setRows] = useState<IngestRow[]>([]);
  const [parseError, setParseError] = useState<string | null>(null);
  const [summary, setSummary] = useState<IngestSummary | null>(null);
  const [loading, setLoading] = useState<"preview" | "commit" | "sis" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runSis() {
    setLoading("sis");
    setError(null);
    try {
      setSummary(await ingestFromSis(token, false));
    } catch {
      setError("SIS pull failed. Ensure Redis/API are up, then retry.");
    } finally {
      setLoading(null);
    }
  }

  function reparse(text: string) {
    setCsv(text);
    setSummary(null);
    if (!text.trim()) {
      setRows([]);
      setParseError(null);
      return;
    }
    const { rows, error } = parseCsv(text);
    setRows(rows);
    setParseError(error);
  }

  async function run(dryRun: boolean) {
    if (!institution.trim() || rows.length === 0) return;
    setLoading(dryRun ? "preview" : "commit");
    setError(null);
    try {
      const res = await ingestCredentials(token, {
        institution: institution.trim(),
        rows,
        dry_run: dryRun,
      });
      setSummary(res);
    } catch {
      setError("Ingestion failed. Check the institution name and CSV, then retry.");
    } finally {
      setLoading(null);
    }
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    reparse(await file.text());
  }

  const ready = institution.trim().length > 0 && rows.length > 0 && !parseError;

  function unlinkRow(email: string, credentialName: string) {
    // Remove the row from the batch before committing — reflects in both the
    // CSV textarea and the preview so the next Preview / Commit skips it.
    const nextRows = rows.filter(
      (r) => !(r.email === email && (r.credential_name ?? "") === (credentialName ?? "")),
    );
    setRows(nextRows);
    setSummary((prev) =>
      prev
        ? {
            ...prev,
            results: prev.results.filter(
              (r) => !(r.email === email && (r.credential_name ?? "") === (credentialName ?? "")),
            ),
          }
        : prev,
    );
    // Rebuild CSV so a re-Preview / Commit uses the unlinked set.
    if (nextRows.length > 0) {
      const header = "email,credential_name,issuer,issued_date,expires_date";
      const body = nextRows
        .map((r) =>
          [r.email, r.credential_name, r.issuer ?? "", r.issued_date ?? "", r.expires_date ?? ""].join(","),
        )
        .join("\n");
      setCsv(`${header}\n${body}`);
    }
  }

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Credentials" }]} />
        <PageHeader
          eyebrow="SKILLED Pro"
          title="Credential ingestion"
          lead="Import a partner institution's completion data. Matched applicants' credentials are raised to Institution-Verified with a signed audit record. Preview before committing."
        />

        {/* Input card */}
        <div className="rounded-md border border-border-light bg-white p-5 space-y-4">
          <div className="max-w-md">
            <MonoLabel className="mb-2 block">Partner institution</MonoLabel>
            <input
              className="input-cohere"
              placeholder="e.g. West Georgia Technical College"
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
            />
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <MonoLabel>Completion data (CSV)</MonoLabel>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => reparse(SAMPLE)}
                  className="text-micro text-cohere-blue underline underline-offset-2"
                >
                  Load sample
                </button>
                <label className="inline-flex cursor-pointer items-center gap-1.5 text-micro text-slate hover:text-ink">
                  <Upload className="h-3.5 w-3.5" /> Upload .csv
                  <input type="file" accept=".csv,text/csv" className="hidden" onChange={onFile} />
                </label>
              </div>
            </div>
            <textarea
              className="input-cohere min-h-[140px] text-caption"
              placeholder="email,credential_name,issuer,issued_date,expires_date"
              value={csv}
              onChange={(e) => reparse(e.target.value)}
            />
            <div className="mt-2 flex items-center justify-between text-micro">
              <span className="text-slate-muted">
                Columns: email, credential_name, issuer, issued_date, expires_date
              </span>
              {parseError ? (
                <span className="text-error-red">{parseError}</span>
              ) : (
                rows.length > 0 && (
                  <span className="text-cohere-green">
                    <FileText className="mr-1 inline h-3.5 w-3.5" />
                    {rows.length} row{rows.length !== 1 ? "s" : ""} parsed
                  </span>
                )
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 border-t border-hairline pt-4">
            <button
              onClick={() => run(true)}
              disabled={!ready || loading !== null}
              className="btn-pill-outline"
            >
              {loading === "preview" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
              Preview (dry run)
            </button>
            <button
              onClick={() => run(false)}
              disabled={!ready || loading !== null}
              className="btn-primary"
            >
              {loading === "commit" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              Commit ingestion
            </button>
            {error && <span className="text-caption text-error-red">{error}</span>}
          </div>
        </div>

        {/* Alternate lanes */}
        <div className="rounded-md border border-border-light bg-white p-5">
          <MonoLabel className="mb-1 block">Other ingestion lanes</MonoLabel>
          <p className="mb-3 text-caption text-slate">
            Beyond the CSV / API lane above, credentials also flow from a direct SIS feed and an
            SFTP file-drop — all through the same match → normalize → Institution-Verified pipeline.
            A real SIS connector (Ellucian Ethos → Banner/Colleague) is an adapter swap once
            credentials are configured.
          </p>
          <button onClick={runSis} disabled={loading !== null} className="btn-pill-outline">
            {loading === "sis" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Database className="h-4 w-4" />}
            Pull from SIS (mock feed)
          </button>
        </div>

        {/* Results */}
        {summary && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <MonoLabel>
                {summary.dry_run ? "Preview result" : "Committed"}
              </MonoLabel>
              {!summary.dry_run && summary.import_run_id && (
                <span className="text-micro text-slate-muted">
                  import run {summary.import_run_id.slice(0, 8)}
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <MetricCard label="Total" value={summary.total} />
              <MetricCard label="Created" value={summary.created} tone="stone" />
              <MetricCard label="Upgraded" value={summary.upgraded} tone="stone" />
              <MetricCard label="Unchanged" value={summary.unchanged} tone="white" />
              <MetricCard label="Unmatched" value={summary.unmatched} tone="white" />
              <MetricCard label="Errors" value={summary.errors} tone="white" />
            </div>

            <div className="overflow-x-auto rounded-md border border-border-light bg-white">
              <table className="w-full text-body">
                <thead>
                  <tr className="border-b border-hairline">
                    <th className="mono-label px-4 py-2.5 text-left">Email</th>
                    <th className="mono-label px-4 py-2.5 text-left">Credential</th>
                    <th className="mono-label px-4 py-2.5 text-left">Applicant</th>
                    <th className="mono-label px-4 py-2.5 text-left">Result</th>
                    {summary.dry_run && <th className="mono-label px-4 py-2.5 text-right">Unlink</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {summary.results.map((r, i) => (
                    <tr key={i} className="align-top">
                      <td className="px-4 py-3 text-caption text-slate">{r.email}</td>
                      <td className="px-4 py-3">
                        <span className="text-cohere-ink">{r.canonical_name ?? r.credential_name}</span>
                        {r.needs_review && (
                          <span className="ml-2 text-micro text-studio-maroon">needs review</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate">{r.applicant_name ?? "—"}</td>
                      <td className="px-4 py-3"><ResultBadge r={r} /></td>
                      {summary.dry_run && (
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => unlinkRow(r.email, r.credential_name)}
                            title="Remove this row from the batch"
                            className="inline-flex items-center gap-1 rounded-full border border-hairline bg-white px-2 py-0.5 text-micro text-slate-muted hover:border-studio-maroon hover:text-studio-maroon transition-colors"
                          >
                            <X className="h-3 w-3" /> Unlink
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {summary.dry_run && summary.matched > 0 && (
              <p className="text-caption text-slate">
                Looks good? Click <strong className="text-ink">Commit ingestion</strong> to write these changes.
              </p>
            )}
          </div>
        )}
      </div>
    </main>
  );
}

function ResultBadge({ r }: { r: { status: string; action: string | null; verification_badge: string | null; detail: string | null } }) {
  if (r.status === "error")
    return (
      <span className="inline-flex items-center gap-1 text-caption text-error-red">
        <XCircle className="h-3.5 w-3.5" /> {r.detail ?? "Error"}
      </span>
    );
  if (r.status === "unmatched")
    return (
      <span className="inline-flex items-center gap-1 text-caption text-studio-maroon">
        <AlertTriangle className="h-3.5 w-3.5" /> No matching applicant
      </span>
    );
  const icon =
    r.action === "created" ? CheckCircle2 : r.action === "upgraded" ? ArrowUpCircle : CircleDashed;
  const Icon = icon;
  const color = r.action === "unchanged" ? "text-slate" : "text-cohere-green";
  return (
    <span className={cn("inline-flex items-center gap-1 text-caption", color)}>
      <Icon className="h-3.5 w-3.5" />
      <span className="capitalize">{r.action}</span>
      {r.verification_badge && (
        <span className="ml-1 rounded-sm bg-wash-green px-1.5 py-0.5 text-micro text-cohere-green">
          {r.verification_badge}
        </span>
      )}
    </span>
  );
}
