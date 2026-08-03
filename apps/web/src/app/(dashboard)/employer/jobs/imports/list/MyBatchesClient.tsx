"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Loader2, CheckCircle2 } from "lucide-react";

import { ImportBatch, batchDisplayTitle, listMyBatches } from "@/lib/api/jobImports";
import { formatDate } from "@/lib/format";
import { PageHeader, ErrorDetails } from "@/components/ui";
import { StatusBadge } from "../[batchId]/StatusBadge";

export function MyBatchesClient({
  token,
  submittedBatchId = null,
  submittedCount = null,
}: {
  token: string;
  /** Batch id just submitted (from ?submitted=…) — highlighted below. */
  submittedBatchId?: string | null;
  submittedCount?: number | null;
}) {
  const [batches, setBatches] = useState<ImportBatch[] | null>(null);
  const [err, setErr] = useState<unknown>(null);

  useEffect(() => {
    listMyBatches(token).then(setBatches).catch((e: unknown) => setErr(e));
  }, [token]);

  const submittedN = submittedCount ?? 0;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Job imports"
          title="My import batches"
          lead="Every batch you've submitted for SKILLED admin review. Approved batches publish to the live job board automatically."
          actions={
            <Link href="/employer/jobs/imports" className="btn-primary inline-flex items-center gap-1.5">
              <Plus className="h-4 w-4" /> New import
            </Link>
          }
        />

        {submittedBatchId && (
          <div
            className="rounded-xl border border-cohere-green/30 bg-wash-green p-4 text-body text-cohere-ink"
            role="status"
          >
            <CheckCircle2 className="mr-1.5 inline h-4 w-4 text-cohere-green" />
            {submittedN > 0
              ? `${submittedN} job${submittedN === 1 ? "" : "s"} submitted for review`
              : "Batch submitted for review"}
            {". You'll be notified here when they're approved, usually within 1 business day."}
          </div>
        )}

        {err != null && (
          <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4 text-body text-cohere-ink">
            {err instanceof Error ? err.message : "Could not load your batches."}
            <ErrorDetails error={err} />
          </div>
        )}

        {batches === null && err == null && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}

        {batches?.length === 0 && (
          <div className="rounded-xl border border-dashed border-hairline bg-white p-12 text-center">
            <p className="text-[1.0625rem] font-medium text-cohere-ink">No batches yet</p>
            <p className="mt-2 text-body text-slate">Start your first import to add jobs to SKILLED.</p>
            <Link href="/employer/jobs/imports" className="btn-primary mt-4 inline-flex items-center gap-1.5">
              <Plus className="h-4 w-4" /> New import
            </Link>
          </div>
        )}

        {batches && batches.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-hairline bg-white shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
            <table className="w-full text-body">
              <thead className="border-b border-hairline bg-stone/40">
                <tr>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Batch</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Submitted</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Jobs</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {batches.map((b) => (
                  <tr
                    key={b.id}
                    className={b.id === submittedBatchId ? "bg-wash-green/60" : undefined}
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-cohere-ink">{batchDisplayTitle(b)}</div>
                      <div className="text-micro text-slate-muted truncate max-w-[320px]">
                        {sourceMeta(b)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-caption text-slate">
                      {b.submitted_at ? formatDate(b.submitted_at) : <span className="text-slate-muted">Not submitted yet</span>}
                    </td>
                    <td className="px-4 py-3 text-caption text-slate tabular-nums">
                      {b.rows_total}
                      {b.status === "approved" || b.status === "published" ? <span className="text-slate-muted">, {b.rows_approved} published</span> : null}
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={b.status} /></td>
                    <td className="px-4 py-3 text-right">
                      <Link href={`/employer/jobs/imports/${b.id}`} className="text-caption text-cohere-blue underline">View</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}

/** Meta line under the title: source kind + created date (+ URL for syncs). */
function sourceMeta(b: ImportBatch): string {
  const created = formatDate(b.created_at);
  const kind =
    b.source === "url" ? "Careers page sync"
    : b.source === "csv" ? "CSV import"
    : b.source === "manual" ? "Entered by hand"
    : b.source;
  const parts = [kind, created ? `created ${created}` : null];
  if (b.source === "url" && b.source_label) parts.push(b.source_label);
  return parts.filter(Boolean).join(" · ");
}
