"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, RefreshCw, ChevronDown, ChevronRight, AlertTriangle } from "lucide-react";

import {
  AdminCareerSource, CareerSourcePullHistoryItem,
  adminCareerSourcePulls, adminListCareerSources, adminPullCareerSource,
} from "@/lib/api/careerSource";
import { SyncTimeline, relativeTime, absoluteTime } from "@/components/careersync/SyncTimeline";
import { PageHeader, statusChipClass } from "@/components/ui";
import { PULL_STATUS_LABELS, humanizeEnum } from "@/lib/humanize";

const PAGE_SIZE = 100;

export function CareerSourcesClient({ token }: { token: string }) {
  const [sources, setSources] = useState<AdminCareerSource[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  // Per-row failure state — a failed sync marks ITS row, not just a page banner.
  const [rowErr, setRowErr] = useState<Record<string, string>>({});
  const [openId, setOpenId] = useState<string | null>(null);
  const [pulls, setPulls] = useState<Record<string, CareerSourcePullHistoryItem[]>>({});
  const [syncing, setSyncing] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await adminListCareerSources(token, PAGE_SIZE, offset);
      setSources(res.items);
      setTotal(res.total);
      setErr(null);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not load career sources");
      setSources([]);
    }
  }, [token, offset]);

  useEffect(() => { refresh(); }, [refresh]);

  async function toggle(sourceId: string) {
    const next = openId === sourceId ? null : sourceId;
    setOpenId(next);
    if (next && !pulls[next]) {
      try {
        const p = await adminCareerSourcePulls(token, next);
        setPulls((prev) => ({ ...prev, [next]: p.items }));
      } catch {
        setPulls((prev) => ({ ...prev, [next]: [] }));
      }
    }
  }

  async function syncNow(sourceId: string) {
    if (syncing) return;
    setSyncing(sourceId);
    setRowErr((prev) => { const n = { ...prev }; delete n[sourceId]; return n; });
    try {
      const result = await adminPullCareerSource(token, sourceId);
      if (result.status !== "ok") {
        setRowErr((prev) => ({
          ...prev,
          [sourceId]: result.error
            || humanizeEnum(result.status, PULL_STATUS_LABELS),
        }));
      }
      const p = await adminCareerSourcePulls(token, sourceId);
      setPulls((prev) => ({ ...prev, [sourceId]: p.items }));
      await refresh();
    } catch (e: unknown) {
      setRowErr((prev) => ({
        ...prev,
        [sourceId]: e instanceof Error ? extractDetail(e) : "Sync failed",
      }));
    } finally {
      setSyncing(null);
    }
  }

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Operations"
          title="Career sources"
          lead="Every connected careers page, its sync health, and a full activity log. First pulls learn each site's structure; after that, re-syncs are incremental and near-instant."
        />

        {err && (
          <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4 text-body text-cohere-ink">{err}</div>
        )}

        {sources === null && (
          <div className="flex items-center gap-2 text-body text-slate">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        )}

        {sources && sources.length === 0 && !err && (
          <div className="rounded-[10px] border border-hairline bg-white px-5 py-3.5" data-tour-id="sources-list">
            <p className="text-body text-slate">No careers pages connected yet.</p>
          </div>
        )}

        {sources && sources.length > 0 && (
          <>
            <section className="rounded-[10px] border border-hairline bg-white" data-tour-id="sources-list">
              {sources.map((s, i) => {
                const open = openId === s.id;
                const Chevron = open ? ChevronDown : ChevronRight;
                return (
                  <div key={s.id} className={i > 0 ? "border-t border-hairline" : ""}>
                    <div
                      onClick={() => toggle(s.id)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(s.id); } }}
                      className="flex cursor-pointer flex-wrap items-center justify-between gap-3 px-5 py-3.5 transition-colors hover:bg-stone/30"
                      aria-expanded={open}
                    >
                      <div className="flex min-w-0 items-start gap-2">
                        <Chevron className="mt-1 h-4 w-4 shrink-0 text-slate-muted" aria-hidden="true" />
                        <div className="min-w-0">
                          <p className="text-body font-medium text-cohere-ink">
                            {s.employer_name}
                            <span className="ml-2 font-normal text-slate-muted">
                              {s.platform ? humanizeEnum(s.platform) : "Platform not detected"}
                            </span>
                          </p>
                          <p className="truncate text-caption text-slate">{s.url}</p>
                          <p className="mt-0.5 text-caption text-slate">{healthSentence(s)}</p>
                          {s.needs_attention && (
                            <p className="mt-0.5 flex items-start gap-1 text-caption text-studio-maroon">
                              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                              {s.attention_reason
                                ?? "A sync was held for review. No jobs were removed."}
                            </p>
                          )}
                          {(s.last_links_broken > 0 || s.jobs_held > 0) && (
                            <p className="mt-0.5 text-caption text-studio-maroon">
                              {[
                                s.jobs_held > 0 && `${s.jobs_held} job${s.jobs_held === 1 ? "" : "s"} held (apply link needs fixing)`,
                                s.last_links_broken > 0 && `${s.last_links_broken} broken link${s.last_links_broken === 1 ? "" : "s"} on last pull`,
                                s.last_jobs_rejected > 0 && `${s.last_jobs_rejected} non-trade posting${s.last_jobs_rejected === 1 ? "" : "s"} filtered`,
                              ].filter(Boolean).join(" · ")}
                            </p>
                          )}
                          {rowErr[s.id] && (
                            <p className="mt-1 flex items-start gap-1 text-caption text-error-red" role="alert">
                              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                              {rowErr[s.id]}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {s.needs_attention && (
                          <span className={statusChipClass("attention")}>Held for review</span>
                        )}
                        {s.last_status && s.last_status !== "ok" && (
                          <span className={statusChipClass(
                            s.last_status === "error" || s.last_status === "blocked" ? "danger" : "attention",
                          )}>
                            {humanizeEnum(s.last_status, PULL_STATUS_LABELS)}
                          </span>
                        )}
                        {s.batch_id && (
                          <Link
                            href={`/admin/job-imports/${s.batch_id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="text-caption text-slate underline hover:text-cohere-ink"
                          >
                            Review batch{s.jobs_staged > 0 ? ` (${s.jobs_staged})` : ""}
                          </Link>
                        )}
                        <button
                          onClick={(e) => { e.stopPropagation(); syncNow(s.id); }}
                          disabled={syncing !== null}
                          className="btn-pill-outline inline-flex items-center gap-1.5 text-caption disabled:opacity-40"
                        >
                          {syncing === s.id
                            ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            : <RefreshCw className="h-3.5 w-3.5" />}
                          Sync now
                        </button>
                      </div>
                    </div>
                    {open && (
                      <div className="border-t border-hairline bg-stone/20">
                        {pulls[s.id] === undefined ? (
                          <p className="flex items-center gap-2 px-5 py-3.5 text-caption text-slate">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading activity…
                          </p>
                        ) : (
                          <SyncTimeline pulls={pulls[s.id]} />
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </section>

            <div className="flex items-center justify-between text-caption text-slate">
              <span>Showing {Math.min(offset + 1, total)}–{Math.min(offset + PAGE_SIZE, total)} of {total.toLocaleString()}</span>
              {total > PAGE_SIZE && (
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
              )}
            </div>
          </>
        )}
      </div>
    </main>
  );
}

function healthSentence(s: AdminCareerSource): string {
  const bits: string[] = [];
  bits.push(
    s.last_pulled_at
      ? `Last synced ${relativeTime(s.last_pulled_at)}`
      : "Never synced",
  );
  bits.push(`${s.jobs_published} live · ${s.jobs_staged} awaiting review`);
  if (s.auto_sync_enabled) {
    bits.push(
      s.next_auto_sync_at
        ? `next auto-sync ${absoluteTime(s.next_auto_sync_at)}`
        : `auto-sync every ${s.auto_sync_interval_hours}h`,
    );
  } else {
    bits.push("auto-sync off");
  }
  if (s.consecutive_failures > 0) {
    bits.push(`${s.consecutive_failures} failed sync${s.consecutive_failures === 1 ? "" : "s"} in a row`);
  }
  return bits.join(" · ");
}

function extractDetail(e: Error): string {
  if ("body" in e) {
    try {
      const body = JSON.parse((e as unknown as { body: string }).body);
      if (typeof body?.detail === "string") return body.detail;
    } catch { /* not json */ }
  }
  return e.message || "Sync failed";
}
