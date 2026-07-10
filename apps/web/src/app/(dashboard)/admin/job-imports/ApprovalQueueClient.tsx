"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";

import { ImportBatch, listAdminBatches } from "@/lib/api/jobImports";
import { PageHeader, Breadcrumb } from "@/components/ui";
import { StatusBadge } from "../../employer/jobs/imports/[batchId]/StatusBadge";

const TABS: { label: string; value: string }[] = [
  { label: "Pending review", value: "pending" },
  { label: "Approved",        value: "approved" },
  { label: "Rejected",        value: "rejected" },
  { label: "Published",       value: "published" },
  { label: "All",             value: "" },
];

export function ApprovalQueueClient({ token }: { token: string }) {
  const [active, setActive] = useState("pending");
  const [batches, setBatches] = useState<ImportBatch[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setBatches(null); setErr(null);
    listAdminBatches(token, active || undefined).then(setBatches).catch((e: Error) => {
      // eslint-disable-next-line no-console
      console.error("[admin/job-imports] listAdminBatches failed", e);
      setErr(e.message);
    });
  }, [token, active]);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Job imports" }]} />
        <PageHeader
          eyebrow="Admin, Approvals"
          title="Employer job imports"
          lead="Batches submitted by employers awaiting your review. Approving publishes their staged rows to the live job board."
        />

        <div className="flex flex-wrap gap-2 border-b border-hairline pb-3">
          {TABS.map((t) => (
            <button
              key={t.value}
              onClick={() => setActive(t.value)}
              className={`rounded-full border px-3 py-1 text-caption transition-colors ${
                active === t.value
                  ? "border-cohere-ink bg-studio-dark-cork text-canvas"
                  : "border-hairline bg-white text-slate hover:border-cohere-ink hover:text-cohere-ink"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {err && (
          <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4">
            <div className="flex items-start justify-between gap-3">
              <p className="text-body text-cohere-ink">{err}</p>
              <button
                onClick={() => {
                  if (typeof navigator !== "undefined") {
                    void navigator.clipboard?.writeText(`/admin/job-imports, ${err}`);
                  }
                }}
                className="shrink-0 text-micro text-slate-muted underline hover:text-cohere-ink"
              >
                Copy error details
              </button>
            </div>
          </div>
        )}
        {batches === null && !err && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}

        {batches?.length === 0 && (
          <div className="rounded-xl border border-dashed border-hairline bg-white p-12 text-center">
            <p className="font-display text-feature text-cohere-ink">Nothing here</p>
            <p className="mt-2 text-body text-slate">No batches match this filter.</p>
          </div>
        )}

        {batches && batches.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-hairline bg-white shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
            <table className="w-full text-body">
              <thead className="border-b border-hairline bg-stone/40">
                <tr>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Employer</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Source</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Submitted</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Rows</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {batches.map((b) => (
                  <tr key={b.id}>
                    <td className="px-4 py-3 font-medium text-cohere-ink">{b.employer_name || b.employer_id.slice(0, 8)}</td>
                    <td className="px-4 py-3 text-caption text-slate capitalize">
                      {b.source}{b.platform ? `, ${b.platform}` : ""}
                    </td>
                    <td className="px-4 py-3 text-caption text-slate">
                      {b.submitted_at ? new Date(b.submitted_at).toLocaleDateString() : <span className="text-slate-muted">—</span>}
                    </td>
                    <td className="px-4 py-3 text-caption text-slate">
                      {b.rows_total} rows
                      {b.rows_rejected > 0 && (
                        <span className="ml-1 text-studio-maroon">, {b.rows_rejected} rejected</span>
                      )}
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={b.status} /></td>
                    <td className="px-4 py-3 text-right">
                      <Link href={`/admin/job-imports/${b.id}`} className="text-caption text-cohere-blue underline">Review</Link>
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
