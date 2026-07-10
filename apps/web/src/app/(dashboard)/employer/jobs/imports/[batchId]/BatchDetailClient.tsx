"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, ArrowLeft, RefreshCw, Clock } from "lucide-react";

import { BatchDetail, getBatch, resyncBatch, setAutoSync } from "@/lib/api/jobImports";
import { PageHeader, useToast } from "@/components/ui";
import { StatusBadge } from "./StatusBadge";

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
  const [err, setErr] = useState<string | null>(null);
  const [resyncing, setResyncing] = useState(false);
  const [autoSync, setAutoSyncState] = useState(false);
  const [savingAutoSync, setSavingAutoSync] = useState(false);

  useEffect(() => {
    getBatch(token, batchId).then(setBatch).catch((e: Error) => setErr(e.message));
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

  async function handleAutoSyncChange(checked: boolean) {
    setAutoSyncState(checked);
    setSavingAutoSync(true);
    try {
      await setAutoSync(token, batchId, checked ? 7 : null);
      toast.success(checked ? "Weekly auto-sync enabled" : "Auto-sync disabled");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not save setting";
      toast.error(msg);
      setAutoSyncState(!checked);
    } finally {
      setSavingAutoSync(false);
    }
  }

  const isUrlBatch = batch?.source === "url";

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Link href="/employer/jobs/imports/list" className="inline-flex items-center gap-1 text-caption text-slate hover:text-cohere-ink">
          <ArrowLeft className="h-3.5 w-3.5" /> All batches
        </Link>

        {err && <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4">{err}</div>}
        {batch === null && !err && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}

        {batch && (
          <>
            <PageHeader
              eyebrow={`${batch.source.toUpperCase()} batch`}
              title={batch.source_label || `Import on ${new Date(batch.created_at).toLocaleDateString()}`}
              lead={`${batch.rows_total} job${batch.rows_total === 1 ? "" : "s"} in this batch.`}
              actions={<StatusBadge status={batch.status} />}
            />

            {/* Sync controls — only for URL-sourced batches */}
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
                <label className="mt-3 flex items-center gap-2 text-caption text-slate">
                  <input
                    type="checkbox"
                    checked={autoSync}
                    onChange={(e) => handleAutoSyncChange(e.target.checked)}
                    disabled={savingAutoSync}
                    className="h-4 w-4 rounded border-hairline text-cohere-green focus:ring-cohere-green"
                  />
                  Set up weekly auto-sync
                </label>
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
                    <tr key={r.id}>
                      <td className="px-4 py-3 align-top">
                        <div className="font-medium text-cohere-ink">{r.title_raw}</div>
                        {r.source_url && <div className="mt-0.5 text-micro text-slate-muted truncate max-w-[280px]">{r.source_url}</div>}
                      </td>
                      <td className="px-4 py-3 align-top text-caption text-slate">
                        {[r.city, r.state].filter(Boolean).join(", ") || "—"}
                      </td>
                      <td className="px-4 py-3 align-top text-caption text-slate">
                        {r.pay_raw || (r.pay_min ? `$${r.pay_min}${r.pay_max ? `–$${r.pay_max}` : ""}` : "—")}
                      </td>
                      <td className="px-4 py-3 align-top text-right"><StatusBadge status={r.status} /></td>
                    </tr>
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
