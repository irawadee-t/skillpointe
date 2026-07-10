"use client";

import { useState } from "react";
import {
  CheckCircle2, AlertTriangle, Loader2, RotateCw, ChevronDown,
} from "lucide-react";

import {
  SyncStatus, PartnerHealthResponse, PartnerHealth, PartnerStatus,
  getSyncStatus, getPartnerHealth, publishEvents,
} from "@/lib/api/sync";
import { PageHeader, MonoLabel, Breadcrumb } from "@/components/ui";
import { cn } from "@/lib/utils";

interface Props {
  initialStatus: SyncStatus;
  initialPartners: PartnerHealthResponse;
  token: string;
}

export function SyncConsole({ initialStatus, initialPartners, token }: Props) {
  const [status, setStatus] = useState<SyncStatus>(initialStatus);
  const [partners, setPartners] = useState<PartnerHealthResponse>(initialPartners);
  const [busy, setBusy] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  async function refresh() {
    try {
      const [s, p] = await Promise.all([
        getSyncStatus(token),
        getPartnerHealth(token),
      ]);
      setStatus(s);
      setPartners(p);
    } catch { /* keep previous */ }
  }

  async function runRetry(key: string, label: string) {
    setBusy(key); setFlash(null);
    try {
      const r = await publishEvents(token);
      await refresh();
      setFlash({
        kind: "ok",
        msg: r.published === 0
          ? "Nothing to retry — everything is up to date."
          : `Retried ${r.published} ${label}.`,
      });
      setTimeout(() => setFlash(null), 4000);
    } catch {
      setFlash({ kind: "err", msg: "Retry failed — check the API and Redis are running." });
    } finally {
      setBusy(null);
    }
  }

  const needsAttention = partners.stuck.length > 0 || partners.total_backlog > 0;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Sync" }]} />
        <PageHeader
          eyebrow="SKILLED Pro"
          title="Partner sync"
          lead="Health of the event pipeline that keeps SKILLED Pro and its partner products in step. Check what's synced, what's waiting, and retry anything that stalled."
        />

        {flash && (
          <div
            role="status"
            className={cn(
              "flex items-center gap-2 rounded-md border p-3 text-body",
              flash.kind === "ok"
                ? "border-studio-forest/25 bg-wash-green text-studio-forest"
                : "border-studio-maroon/30 bg-studio-maroon/5 text-studio-maroon",
            )}
          >
            {flash.kind === "ok"
              ? <CheckCircle2 className="h-4 w-4" strokeWidth={1.75} />
              : <AlertTriangle className="h-4 w-4" strokeWidth={1.75} />}
            <span>{flash.msg}</span>
          </div>
        )}

        {/* Section 1 — Health at a glance */}
        <section aria-labelledby="sync-health-heading" className="space-y-3">
          <div className="flex items-center justify-between">
            <MonoLabel id="sync-health-heading">Health</MonoLabel>
            <button
              type="button"
              onClick={() => refresh()}
              className="btn-ghost btn-sm"
            >
              <RotateCw className="h-4 w-4" strokeWidth={1.75} /> Refresh
            </button>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {partners.partners.length === 0
              ? (
                <div className="rounded-md border border-border-light bg-white p-5 text-body text-slate">
                  No partners connected yet.
                </div>
              )
              : partners.partners.map((p) => (
                <PartnerCard key={p.source} partner={p} />
              ))}
          </div>
        </section>

        {/* Section 2 — Needs attention */}
        {needsAttention && (
          <section aria-labelledby="sync-attention-heading" className="space-y-3">
            <div className="flex items-center justify-between">
              <MonoLabel id="sync-attention-heading">Needs attention</MonoLabel>
              {partners.total_backlog > 0 && (
                <button
                  type="button"
                  onClick={() => runRetry("retry-all", partners.total_backlog === 1 ? "event" : "events")}
                  disabled={busy !== null}
                  className="btn-md"
                >
                  {busy === "retry-all"
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <RotateCw className="h-4 w-4" strokeWidth={1.75} />}
                  Retry all ({partners.total_backlog})
                </button>
              )}
            </div>

            <div className="rounded-md border border-border-light bg-white">
              {partners.stuck.length === 0
                ? (
                  <p className="p-5 text-body text-slate">
                    {partners.total_backlog} event{partners.total_backlog === 1 ? "" : "s"}{" "}
                    waiting to relay. Nothing stuck long enough to flag individually — hit
                    &ldquo;Retry all&rdquo; to push them now.
                  </p>
                )
                : (
                  <ul className="divide-y divide-hairline">
                    {partners.stuck.map((e) => (
                      <li key={e.event_id} className="flex items-center justify-between gap-3 px-4 py-3">
                        <div className="min-w-0">
                          <div className="text-body text-ink">
                            <span className="font-semibold">{e.event_type}</span>
                            <span className="text-slate">, {e.partner}</span>
                          </div>
                          <div className="text-caption text-slate-muted">
                            Waiting {formatDuration(e.waiting_seconds)}, {e.aggregate_type}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => runRetry(`retry-${e.event_id}`, "event")}
                          disabled={busy !== null}
                          className="btn-ghost btn-sm shrink-0"
                        >
                          {busy === `retry-${e.event_id}`
                            ? <Loader2 className="h-4 w-4 animate-spin" />
                            : <RotateCw className="h-4 w-4" strokeWidth={1.75} />}
                          Retry
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
            </div>
          </section>
        )}

        {/* Section 3 — Recent activity (collapsed) */}
        <section aria-labelledby="sync-recent-heading">
          <details className="group rounded-md border border-border-light bg-white">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
              <span id="sync-recent-heading" className="flex items-center gap-2 text-body text-ink">
                <MonoLabel as="span">Recent activity</MonoLabel>
                <span aria-hidden className="text-slate-muted">—</span>
                <span className="text-caption text-slate">
                  Last {status.recent.length} event{status.recent.length === 1 ? "" : "s"}
                </span>
              </span>
              <ChevronDown
                className="h-4 w-4 text-slate transition-transform group-open:rotate-180"
                strokeWidth={1.75}
              />
            </summary>
            <div className="border-t border-hairline">
              {status.recent.length === 0
                ? (
                  <p className="px-4 py-5 text-body text-slate">
                    No events yet. When a credential or consent setting changes,
                    it will show up here.
                  </p>
                )
                : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-body">
                      <thead>
                        <tr className="border-b border-hairline">
                          <th className="mono-label px-4 py-2.5 text-left">When</th>
                          <th className="mono-label px-4 py-2.5 text-left">Partner</th>
                          <th className="mono-label px-4 py-2.5 text-left">Kind</th>
                          <th className="mono-label px-4 py-2.5 text-left">Status</th>
                          <th className="mono-label px-4 py-2.5 text-left">Event ID</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-hairline">
                        {status.recent.map((e) => (
                          <tr key={e.event_id}>
                            <td className="px-4 py-2.5 text-caption text-slate tabular-nums">
                              {new Date(e.occurred_at).toLocaleTimeString()}
                            </td>
                            <td className="px-4 py-2.5 text-caption text-ink">
                              {partnerDisplayName(e.source)}
                            </td>
                            <td className="px-4 py-2.5 text-caption text-ink">
                              {e.event_type}
                            </td>
                            <td className="px-4 py-2.5">
                              {e.published
                                ? <span className="text-caption text-studio-forest">Synced</span>
                                : <span className="text-caption text-studio-grey-brown">Waiting</span>}
                            </td>
                            <td className="px-4 py-2.5 text-micro text-slate-muted">
                              <span className="rounded-xs bg-parchment px-1.5 py-0.5">
                                {e.event_id.slice(0, 8)}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
            </div>
          </details>
        </section>
      </div>
    </main>
  );
}

// ─── Cards & helpers ──────────────────────────────────────────────────────

function PartnerCard({ partner }: { partner: PartnerHealth }) {
  return (
    <div className="rounded-md border border-border-light bg-white p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-display text-subhead text-ink">{partner.name}</h3>
          <p className="mt-0.5 text-micro text-slate-muted">{partner.source}</p>
        </div>
        <StatusPill status={partner.status} />
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-hairline pt-4">
        <StatItem
          label="Last synced"
          value={partner.last_sync_at ? relativeTime(partner.last_sync_at) : "—"}
        />
        <StatItem
          label="Last 24h"
          value={partner.events_24h === 0 ? "0" : String(partner.events_24h)}
          sub={partner.events_24h === 1 ? "event" : "events"}
        />
        <StatItem
          label="Backlog"
          value={String(partner.backlog)}
          sub={partner.backlog === 0 ? "clear" : "waiting"}
          emphasize={partner.backlog > 0}
        />
      </dl>
    </div>
  );
}

function StatItem({
  label, value, sub, emphasize,
}: { label: string; value: string; sub?: string; emphasize?: boolean }) {
  return (
    <div>
      <dt className="mono-label text-slate-muted">{label}</dt>
      <dd
        className={cn(
          "mt-1 font-display text-feature",
          emphasize ? "text-studio-maroon" : "text-ink",
        )}
      >
        {value}
      </dd>
      {sub && <dd className="text-caption text-slate-muted">{sub}</dd>}
    </div>
  );
}

function StatusPill({ status }: { status: PartnerStatus }) {
  const styles: Record<PartnerStatus, string> = {
    healthy: "bg-studio-forest/10 text-studio-forest border-studio-forest/25",
    delayed: "bg-studio-grey-brown/10 text-studio-grey-brown border-studio-grey-brown/25",
    down:    "bg-studio-maroon/10 text-studio-maroon border-studio-maroon/30",
  };
  const label: Record<PartnerStatus, string> = {
    healthy: "Healthy",
    delayed: "Delayed",
    down:    "Down",
  };
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-xs border px-2 py-1 text-micro font-semibold uppercase tracking-mono",
        styles[status],
      )}
    >
      <span
        className={cn(
          "inline-block h-1.5 w-1.5 rounded-full",
          status === "healthy" && "bg-studio-forest",
          status === "delayed" && "bg-studio-grey-brown",
          status === "down"    && "bg-studio-maroon",
        )}
      />
      {label[status]}
    </span>
  );
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diff = Math.max(0, Date.now() - then);
  const s = Math.floor(diff / 1000);
  if (s < 45) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

const PARTNER_NAMES: Record<string, string> = {
  skilled_pro: "SKILLED Pro",
  skilled_nation: "SKILLED Nation",
};

function partnerDisplayName(source: string): string {
  return PARTNER_NAMES[source] ?? source.replace(/_/g, " ");
}
