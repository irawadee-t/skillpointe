"use client";

import { useState } from "react";
import {
  GraduationCap, Users, Upload, Eye, CheckCircle2, Loader2, FileText, History,
} from "lucide-react";

import {
  Institution, RosterRow, ImportRun, uploadCompletions, getRoster, getImports,
} from "@/lib/api/institution";
import type { IngestSummary } from "@/lib/api/ingest";
import { PageHeader, MonoLabel, MetricCard } from "@/components/ui";
import { formatDateShort } from "@/lib/format";
import { cn } from "@/lib/utils";

const SAMPLE = `email,credential_name,issuer,issued_date
applicant@test.local,Industrial Maintenance Certificate,West Georgia Technical College,2025-05-01
riyakaru@stanford.edu,OSHA 30-Hour,West Georgia Technical College,2025-04-15`;

export function InstitutionClient({
  institution, initialRoster, initialImports, token,
}: {
  institution: Institution;
  initialRoster: RosterRow[];
  initialImports: ImportRun[];
  token: string;
}) {
  const [inst, setInst] = useState(institution);
  const [csv, setCsv] = useState("");
  const [summary, setSummary] = useState<IngestSummary | null>(null);
  const [roster, setRoster] = useState(initialRoster);
  const [imports, setImports] = useState(initialImports);
  const [loading, setLoading] = useState<"preview" | "commit" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(dryRun: boolean) {
    if (!csv.trim()) return;
    setLoading(dryRun ? "preview" : "commit");
    setError(null);
    try {
      const res = await uploadCompletions(token, csv, dryRun);
      setSummary(res);
      if (!dryRun) {
        const [r, im] = await Promise.all([getRoster(token), getImports(token)]);
        setRoster(r); setImports(im);
        setInst((p) => ({ ...p, credentials_issued: p.credentials_issued })); // refreshed below
      }
    } catch {
      setError("Upload failed. Check the CSV columns and retry.");
    } finally {
      setLoading(null);
    }
  }

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Partner portal"
          title={inst.name}
          lead="Upload your program completions to issue Institution-Verified credentials on SKILLED. Every upload runs through the same match → normalize → signed-record pipeline, scoped to your institution."
        />

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <MetricCard label="Credentials issued" value={inst.credentials_issued} icon={GraduationCap} />
          <MetricCard label="Students credentialed" value={inst.learners} icon={Users} tone="stone" />
          <MetricCard label="Recent imports" value={imports.length} icon={History} tone="white" className="col-span-2 sm:col-span-1" />
        </div>

        {/* Upload */}
        <div className="rounded-md border border-border-light bg-white p-5">
          <div className="mb-2 flex items-center justify-between">
            <MonoLabel className="flex items-center gap-1.5"><Upload className="h-3.5 w-3.5" /> Upload completions (CSV)</MonoLabel>
            <button onClick={() => setCsv(SAMPLE)} className="text-micro text-cohere-blue underline underline-offset-2">Load sample</button>
          </div>
          <textarea
            className="input-cohere min-h-[120px] w-full text-caption"
            placeholder="email,credential_name,issuer,issued_date,expires_date"
            value={csv}
            onChange={(e) => { setCsv(e.target.value); setSummary(null); }}
          />
          <p className="mt-1 text-micro text-slate-muted">Columns: email, credential_name, issuer, issued_date, expires_date</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button onClick={() => run(true)} disabled={!csv.trim() || loading !== null} className="btn-pill-outline">
              {loading === "preview" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />} Preview
            </button>
            <button onClick={() => run(false)} disabled={!csv.trim() || loading !== null} className="btn-primary">
              {loading === "commit" ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />} Commit upload
            </button>
            {error && <span className="text-caption text-error-red">{error}</span>}
          </div>

          {summary && (
            <div className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-6">
              {([["Total", summary.total], ["Created", summary.created], ["Upgraded", summary.upgraded],
                 ["Unchanged", summary.unchanged], ["Unmatched", summary.unmatched], ["Errors", summary.errors]] as const).map(
                ([label, v]) => (
                  <div key={label} className="rounded-sm border border-border-light p-2 text-center">
                    <div className="font-display text-card tabular-nums text-cohere-ink">{v}</div>
                    <div className="mono-label">{label}</div>
                  </div>
                ))}
              {summary.dry_run && <p className="col-span-full text-micro text-slate-muted">Preview only. Nothing was written.</p>}
            </div>
          )}
        </div>

        {/* Roster */}
        <div>
          <MonoLabel className="mb-2 flex items-center gap-1.5"><FileText className="h-3.5 w-3.5" /> Credentials you've issued</MonoLabel>
          <div className="overflow-x-auto rounded-md border border-border-light bg-white">
            <table className="w-full text-body">
              <thead>
                <tr className="border-b border-hairline">
                  <th className="mono-label px-4 py-2.5 text-left">Learner</th>
                  <th className="mono-label px-4 py-2.5 text-left">Credential</th>
                  <th className="mono-label px-4 py-2.5 text-left">Tier</th>
                  <th className="mono-label px-4 py-2.5 text-right">Issued</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {roster.length === 0 ? (
                  <tr><td colSpan={4} className="px-4 py-8 text-center text-body text-slate">No credentials issued yet. Upload a batch above.</td></tr>
                ) : roster.map((r, i) => (
                  <tr key={i}>
                    <td className="px-4 py-2.5 font-semibold text-cohere-ink">{r.applicant_name}</td>
                    <td className="px-4 py-2.5 text-slate">{r.credential_name}</td>
                    <td className="px-4 py-2.5">
                      <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
                        /self.reported/i.test(r.verification_badge ?? "")
                          ? "border-hairline bg-white text-slate"
                          : "border-cohere-green bg-cohere-green text-white")}>
                        {r.verification_badge}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right text-caption text-slate tabular-nums">{r.issued_date ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Import history */}
        {imports.length > 0 && (
          <div>
            <MonoLabel className="mb-2 flex items-center gap-1.5"><History className="h-3.5 w-3.5" /> Import history</MonoLabel>
            <ul className="divide-y divide-hairline rounded-md border border-border-light bg-white">
              {imports.map((im) => (
                <li key={im.id} className="flex items-center justify-between px-4 py-2.5 text-caption">
                  <span className="text-slate-muted">{im.id.slice(0, 8)}</span>
                  <span className="text-slate">{im.success_count}/{im.row_count} matched, {im.error_count} errors</span>
                  <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
                    im.status === "complete"
                      ? "border-cohere-green bg-cohere-green text-white"
                      : im.status === "failed" || im.status === "error"
                        ? "border-error-red bg-error-red text-white"
                        : "border-cohere-blue bg-cohere-blue text-white")}>
                    {im.status}
                  </span>
                  <span className="text-slate-muted">{formatDateShort(im.created_at)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </main>
  );
}
