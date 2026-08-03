"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, ArrowLeft, RefreshCw, Clock, ChevronDown, ChevronRight } from "lucide-react";

import { BatchDetail, ImportRow, batchDisplayTitle, getBatch, resyncBatch } from "@/lib/api/jobImports";
import { PageHeader, ErrorDetails, useToast } from "@/components/ui";
import { StatusBadge } from "./StatusBadge";

function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    url: "Careers page",
    csv: "CSV",
    sheet: "Sheet",
    doc: "Document",
    manual: "Manual",
  };
  return labels[source] ?? source;
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function BatchDetailClient({ token, batchId }: { token: string; batchId: string }) {
  const toast = useToast();
  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [resyncing, setResyncing] = useState(false);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  useEffect(() => {
    getBatch(token, batchId).then(setBatch).catch((e: unknown) => setErr(e));
  }, [token, batchId]);

  async function handleResync() {
    setResyncing(true);
    try {
      const b = await resyncBatch(token, batchId);
      setBatch(b);
      toast.success("Re-synced from source");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not re-sync";
      toast.error(msg);
    } finally {
      setResyncing(false);
    }
  }

  const isUrlBatch = batch?.source === "url";

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Link href="/employer/jobs/imports/list" className="inline-flex items-center gap-1 text-caption text-slate hover:text-cohere-ink">
          <ArrowLeft className="h-3.5 w-3.5" /> All batches
        </Link>

        {err != null && (
          <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4 text-body text-cohere-ink">
            {err instanceof Error ? err.message : "Could not load this batch."}
            <ErrorDetails error={err} />
          </div>
        )}
        {batch === null && !err && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}

        {batch && (
          <>
            <PageHeader
              eyebrow={`${sourceLabel(batch.source)} batch`}
              title={batchDisplayTitle(batch)}
              lead={`${batch.rows_total} job${batch.rows_total === 1 ? "" : "s"} in this batch${batch.source_label && batch.source === "url" ? ` · ${batch.source_label}` : ""}.`}
              actions={<StatusBadge status={batch.status} />}
            />

            {/* Sync controls — only for URL-sourced batches. Auto-sync has ONE
                owner: the connected careers page's interval setting. */}
            {isUrlBatch && (
              <div className="rounded-xl border border-hairline bg-white p-5 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-caption text-slate">
                    <Clock className="h-4 w-4 text-slate-muted" />
                    Last synced: <span className="font-medium text-cohere-ink">{timeAgo(batch.updated_at ?? batch.created_at)}</span>
                  </div>
                  <button
                    onClick={handleResync}
                    disabled={resyncing}
                    className="btn-pill-outline inline-flex items-center gap-1.5 text-caption disabled:opacity-40"
                  >
                    {resyncing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                    {resyncing ? "Re-syncing…" : "Re-sync from source"}
                  </button>
                </div>
                <p className="mt-3 text-caption text-slate">
                  Automatic syncing is controlled by your connected careers page&rsquo;s
                  schedule.{" "}
                  <Link href="/employer/jobs/imports" className="text-cohere-blue underline">
                    Manage sync settings
                  </Link>
                </p>
              </div>
            )}

            {batch.reviewer_note && (
              <div className={`rounded-xl border p-5 ${batch.status === "rejected" ? "border-studio-maroon/30 bg-studio-maroon/[0.06]" : "border-cohere-green/30 bg-wash-green"}`}>
                <div className="mono-label mb-1">Admin note</div>
                <p className="text-body text-cohere-ink">{batch.reviewer_note}</p>
              </div>
            )}

            <div className="overflow-hidden rounded-xl border border-hairline bg-white shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
              <table className="w-full text-body">
                <thead className="border-b border-hairline bg-stone/40">
                  <tr>
                    <th className="px-4 py-3 text-left text-caption font-medium text-slate">Title</th>
                    <th className="px-4 py-3 text-left text-caption font-medium text-slate">Location</th>
                    <th className="px-4 py-3 text-left text-caption font-medium text-slate">Pay</th>
                    <th className="px-4 py-3 text-right text-caption font-medium text-slate">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {batch.rows.map((r) => (
                    <ExpandableRow
                      key={r.id}
                      row={r}
                      expanded={expandedRow === r.id}
                      onToggle={() => setExpandedRow(expandedRow === r.id ? null : r.id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </main>
  );
}

/** Full read access to every captured field — click a row to open it. */
function ExpandableRow({
  row: r, expanded, onToggle,
}: {
  row: ImportRow; expanded: boolean; onToggle: () => void;
}) {
  const Chevron = expanded ? ChevronDown : ChevronRight;
  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer transition-colors hover:bg-stone/30"
        aria-expanded={expanded}
      >
        <td className="px-4 py-3 align-top">
          <div className="flex items-start gap-1.5">
            <Chevron className="mt-1 h-3.5 w-3.5 shrink-0 text-slate-muted" aria-hidden="true" />
            <div className="min-w-0">
              <div className="font-medium text-cohere-ink">{r.title_raw}</div>
              {r.source_url && <div className="mt-0.5 text-micro text-slate-muted truncate max-w-[280px]">{r.source_url}</div>}
              {(r.link_status === "broken" || r.link_status === "blocked") && (
                <div className="mt-0.5 text-micro font-medium text-studio-maroon">
                  Apply link not working. Held for review
                </div>
              )}
            </div>
          </div>
        </td>
        <td className="px-4 py-3 align-top text-caption text-slate">
          {[r.city, r.state].filter(Boolean).join(", ") || "—"}
        </td>
        <td className="px-4 py-3 align-top text-caption text-slate">
          {r.pay_raw || (r.pay_min ? `$${r.pay_min}${r.pay_max ? `–$${r.pay_max}` : ""}` : "—")}
        </td>
        <td className="px-4 py-3 align-top text-right"><StatusBadge status={r.status} /></td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={4} className="bg-stone/20 px-4 py-4">
            <dl className="grid gap-x-8 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
              <RowFact label="Employment type" value={r.employment_type} />
              <RowFact label="Experience level" value={r.experience_level} />
              <RowFact label="Work setting" value={r.work_setting} />
              <RowFact label="Trade category" value={r.job_category} />
              <RowFact label="Requisition id" value={r.req_id} />
              <RowFact label="Posted on site" value={r.posted_date} />
              <RowFact label="First seen" value={r.first_seen_at ? timeAgo(r.first_seen_at) : null} />
              <RowFact label="Last synced" value={r.last_synced_at ? timeAgo(r.last_synced_at) : null} />
              <RowFact
                label="Apply link"
                value={
                  r.link_status
                    ? `${r.link_status === "ok" ? "Working" : "Not working"}${r.link_checked_at ? `, checked ${timeAgo(r.link_checked_at)}` : ""}`
                    : "Not checked yet"
                }
              />
            </dl>
            {r.source_url && (
              <p className="mt-3 text-caption">
                <a href={r.source_url} target="_blank" rel="noopener noreferrer"
                   className="text-cohere-blue underline">
                  Open the posting on your site
                </a>
              </p>
            )}
            {r.description_raw && <RowText label="Description" text={r.description_raw} />}
            {r.responsibilities_raw && <RowText label="Responsibilities" text={r.responsibilities_raw} />}
            {r.requirements_raw && <RowText label="Requirements" text={r.requirements_raw} />}
            {r.preferred_qualifications_raw && <RowText label="Preferred qualifications" text={r.preferred_qualifications_raw} />}
          </td>
        </tr>
      )}
    </>
  );
}

function RowFact({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex gap-2 text-caption">
      <dt className="shrink-0 text-slate-muted">{label}:</dt>
      <dd className="text-cohere-ink">{value || "—"}</dd>
    </div>
  );
}

function RowText({ label, text }: { label: string; text: string }) {
  return (
    <div className="mt-3">
      <p className="text-caption font-medium text-cohere-ink">{label}</p>
      <p className="mt-1 whitespace-pre-line text-caption leading-relaxed text-slate">
        {text.length > 1200 ? `${text.slice(0, 1200)}…` : text}
      </p>
    </div>
  );
}
