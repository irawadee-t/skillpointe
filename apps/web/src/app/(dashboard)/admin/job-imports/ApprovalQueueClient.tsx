"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Link2 } from "lucide-react";

import { AdminBatchList, ImportBatch, batchDisplayTitle, listAdminBatches } from "@/lib/api/jobImports";
import { formatDateShort } from "@/lib/format";
import { PageHeader, Breadcrumb, statusChipClass, type StatusTone } from "@/components/ui";
import { REVIEW_STATE_LABELS, humanizeEnum } from "@/lib/humanize";

/**
 * The admin approval queue. "Awaiting review" is the default view and uses
 * the SAME definition as the dashboard inbox and career sources (backend
 * util.review_queue): submitted batches + careers-page pulls with staged
 * rows. "All" really is every batch, every status.
 */
const TABS: { label: string; value: string }[] = [
  { label: "Awaiting review", value: "awaiting" },
  { label: "Staged from careers pages", value: "staged" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
  { label: "Published", value: "published" },
  { label: "All", value: "all" },
];

const PAGE_SIZE = 50;

/** review_state → semantic chip tone (statusTones slots, no bespoke colors). */
const REVIEW_STATE_TONES: Record<string, StatusTone> = {
  awaiting_review: "attention",
  staged_from_careers: "attention",
  draft: "muted",
  pending: "attention",
  approved: "positive",
  published: "positiveSolid",
  rejected: "muted",
};

export function ReviewStateChip({ batch }: { batch: ImportBatch }) {
  const state = batch.review_state ?? batch.status;
  const tone = REVIEW_STATE_TONES[state] ?? "neutral";
  return (
    <span className={statusChipClass(tone)}>
      {humanizeEnum(state, REVIEW_STATE_LABELS)}
    </span>
  );
}

export function ApprovalQueueClient({ token }: { token: string }) {
  const [active, setActive] = useState("awaiting");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<AdminBatchList | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setData(null); setErr(null);
    listAdminBatches(token, active, PAGE_SIZE, offset).then(setData).catch((e: Error) => {
      // eslint-disable-next-line no-console
      console.error("[admin/job-imports] listAdminBatches failed", e);
      setErr(e.message);
    });
  }, [token, active, offset]);

  const batches = data?.items ?? null;
  const total = data?.total ?? 0;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Job imports" }]} />
        <PageHeader
          eyebrow="Admin, Approvals"
          title="Job imports"
          lead={
            data
              ? `${data.awaiting.rows.toLocaleString()} job${data.awaiting.rows === 1 ? "" : "s"} awaiting review across ${data.awaiting.batches.toLocaleString()} batch${data.awaiting.batches === 1 ? "" : "es"}. Submitted batches and careers-page pulls, one queue.`
              : "Submitted batches and careers-page pulls awaiting your review. Approving publishes staged rows to the live job board."
          }
        />

        <div className="flex flex-wrap gap-2 border-b border-hairline pb-3" role="tablist" aria-label="Batch filters">
          {TABS.map((t) => (
            <button
              key={t.value}
              role="tab"
              aria-selected={active === t.value}
              onClick={() => { setActive(t.value); setOffset(0); }}
              className={`rounded-full border px-3 py-1 text-caption transition-colors ${
                active === t.value
                  ? "border-ink bg-ink text-white"
                  : "border-hairline bg-white text-slate hover:border-cohere-ink hover:text-cohere-ink"
              }`}
            >
              {t.label}
              {t.value === "awaiting" && data && data.awaiting.batches > 0 && (
                <span className="ml-1.5 tabular-nums">{data.awaiting.batches}</span>
              )}
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
          <div className="rounded-xl border border-dashed border-hairline bg-white p-12 text-center" data-tour-id="imports-list">
            <p className="text-[1.0625rem] font-medium text-cohere-ink">
              {active === "awaiting" ? "Queue clear. Nothing awaiting review" : "Nothing here"}
            </p>
            <p className="mt-2 text-body text-slate">No batches match this filter.</p>
          </div>
        )}

        {batches && batches.length > 0 && (
          <>
            <div className="overflow-hidden rounded-xl border border-hairline bg-white" data-tour-id="imports-list">
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
                      <td className="px-4 py-3 font-medium text-cohere-ink">
                        {b.employer_name || b.employer_id.slice(0, 8)}
                        {b.from_career_source && (
                          <span className="ml-1.5 inline-flex items-center gap-0.5 align-middle text-micro text-slate-muted" title="Connected careers page">
                            <Link2 className="h-3 w-3" aria-hidden /> careers page
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-caption text-slate">
                        {batchDisplayTitle(b)}
                      </td>
                      <td className="px-4 py-3 text-caption text-slate">
                        {b.submitted_at
                          ? formatDateShort(b.submitted_at)
                          : b.review_state === "staged_from_careers"
                            ? <span title="Careers-page pulls stage rows without a submit step">auto-staged</span>
                            : <span className="text-slate-muted">—</span>}
                      </td>
                      <td className="px-4 py-3 text-caption text-slate">
                        {(b.rows_staged ?? b.rows_total).toLocaleString()} to review
                        {(b.rows_held ?? 0) > 0 && (
                          <span className="ml-1 text-studio-maroon">· {b.rows_held} held</span>
                        )}
                        {b.rows_rejected > 0 && (
                          <span className="ml-1 text-slate-muted">· {b.rows_rejected} rejected</span>
                        )}
                      </td>
                      <td className="px-4 py-3"><ReviewStateChip batch={b} /></td>
                      <td className="px-4 py-3 text-right">
                        <Link href={`/admin/job-imports/${b.id}`} className="text-caption text-cohere-blue underline">Review</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between text-caption text-slate">
              <span>
                Showing {Math.min(offset + 1, total)}–{Math.min(offset + PAGE_SIZE, total)} of {total.toLocaleString()}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  disabled={offset === 0}
                  className="rounded-full border border-hairline bg-white px-3 py-1 transition-colors hover:border-cohere-ink disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  disabled={offset + PAGE_SIZE >= total}
                  className="rounded-full border border-hairline bg-white px-3 py-1 transition-colors hover:border-cohere-ink disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
