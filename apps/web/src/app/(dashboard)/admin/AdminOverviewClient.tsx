"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Users, RefreshCw, ClipboardCheck, CheckCircle2,
  Loader2, FileText, Clock, ChevronRight, X,
} from "lucide-react";
import { ConfirmDialog, MetricCard, PageHeader } from "@/components/ui";
import { TourWelcomeBand } from "@/components/tour/TourWelcomeBand";
import { MarketplaceFunnel, ShareBars } from "@/components/viz";
import { SupplyDemandBars } from "@/components/viz2";
import {
  fetchSupplyDemand,
  type SupplyDemandResponse,
} from "@/components/viz2/marketData";
import { DormantApplicationsCard } from "@/components/admin/DormantApplicationsCard";
import { fetchAdminOverview, fetchRecomputeStatus, type PlatformOverview } from "@/lib/api/admin";

const n = (x: number | null | undefined) => (x === null || x === undefined ? "—" : x.toLocaleString());

/** A flat metric phrase; wraps in a quiet link when a destination exists. */
function Metric({ label, value, sub, href }: {
  label: string; value: string; sub?: string; href?: string;
}) {
  // Decapitalize ordinary Title-case labels so the phrase reads naturally
  // ("337 workers"), but leave brand/acronym labels alone.
  const phrase = /^[A-Z][a-z]/.test(label) ? label.charAt(0).toLowerCase() + label.slice(1) : label;
  const card = (
    <MetricCard
      label={phrase}
      value={value}
      sub={sub}
      className={href ? "h-full transition-colors hover:border-cohere-ink/30" : "h-full"}
    />
  );
  return href ? <Link href={href} className="block h-full">{card}</Link> : card;
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-feature text-cohere-ink">{title}</h2>
        {hint && <span className="text-caption text-slate-muted">{hint}</span>}
      </div>
      {children}
    </section>
  );
}

/**
 * The stage pair losing the most people — the funnel's one "so what".
 * Uses absolute loss, not rate: at small scale a "0 of 1" transition would
 * always win on rate while the real story is the 336 lost a stage earlier.
 */
function funnelTakeaway(funnel: { label: string; count: number }[]): string | null {
  if (funnel.length < 2 || funnel[0].count === 0) return null;
  let worstIdx = -1;
  let worstLoss = -1;
  for (let i = 0; i < funnel.length - 1; i++) {
    const from = funnel[i];
    const to = funnel[i + 1];
    if (from.count === 0) break; // everything past an empty stage is trivially 0
    const loss = from.count - to.count;
    if (loss > worstLoss) {
      worstLoss = loss;
      worstIdx = i;
    }
  }
  if (worstIdx < 0 || worstLoss <= 0) return null;
  const from = funnel[worstIdx];
  const to = funnel[worstIdx + 1];
  const rate = to.count / from.count;
  const pctLabel = rate > 0 && rate < 0.005 ? "<1%" : `${Math.round(rate * 100)}%`;
  return `Biggest drop-off: ${from.label.toLowerCase()} → ${to.label.toLowerCase()}: ${to.count.toLocaleString()} of ${from.count.toLocaleString()} continue (${pctLabel}).`;
}

const EVENT_LABELS: Record<string, string> = {
  interest_set: "Interest set", apply_click: "Apply clicks", dm_sent: "Messages sent",
  outreach_sent: "Employer outreach", hire_reported: "Hires reported", candidate_verified: "Candidate verifications",
  chat_message_sent: "Chat messages", match_view: "Match views", profile_update: "Profile updates",
  application_submitted: "Applications submitted", credential_added: "Credentials added",
  profile_completed: "Profiles completed", job_view: "Job views", candidate_viewed: "Candidates viewed",
};

export function AdminOverviewClient({ data: initialData, token }: { data: PlatformOverview; token: string }) {
  // Auto-poll every 30s so KPIs don't go stale after ingest / imports.
  // Pauses when the tab is hidden and resumes on focus.
  const [data, setData] = useState<PlatformOverview>(initialData);
  const [refreshing, setRefreshing] = useState(false);
  // Set on the client only — rendering `new Date()` during SSR causes a
  // hydration mismatch (server and client seconds differ).
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  useEffect(() => setLastUpdated(new Date()), []);
  const inFlightRef = useRef(false);
  const [cmdKHintVisible, setCmdKHintVisible] = useState(false);

  // Show a one-time tip for the ⌘K palette. Rules:
  //   1. Only for admins who've never opened the palette (own localStorage flag)
  //   2. Only for the first week after we know about this browser
  //   3. Dismissible — dismiss flag suppresses forever
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const OPENED = "sn.cmdk.opened";
      const DISMISSED = "sn.cmdk.hint.dismissed";
      const SEEN = "sn.cmdk.hint.first_seen";
      if (window.localStorage.getItem(OPENED)) return;
      if (window.localStorage.getItem(DISMISSED)) return;
      const firstSeenRaw = window.localStorage.getItem(SEEN);
      const firstSeen = firstSeenRaw ? parseInt(firstSeenRaw, 10) : Date.now();
      if (!firstSeenRaw) window.localStorage.setItem(SEEN, String(firstSeen));
      const oneWeek = 7 * 24 * 60 * 60 * 1000;
      if (Date.now() - firstSeen > oneWeek) return;
      setCmdKHintVisible(true);
    } catch { /* silent */ }
  }, []);

  // If the user actually opens the palette while the pill is up, record it
  // and hide the tip. Detects both ⌘K and Ctrl+K.
  useEffect(() => {
    if (!cmdKHintVisible) return;
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        try { window.localStorage.setItem("sn.cmdk.opened", "1"); } catch { /* silent */ }
        setCmdKHintVisible(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cmdKHintVisible]);

  function dismissCmdKHint() {
    try { window.localStorage.setItem("sn.cmdk.hint.dismissed", "1"); } catch { /* silent */ }
    setCmdKHintVisible(false);
  }

  const refresh = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setRefreshing(true);
    try {
      const next = await fetchAdminOverview(token);
      setData(next);
      setLastUpdated(new Date());
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("[admin/overview] refresh failed", err);
    } finally {
      inFlightRef.current = false;
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;
    const start = () => {
      if (interval != null) return;
      interval = setInterval(() => { void refresh(); }, 30_000);
    };
    const stop = () => {
      if (interval != null) { clearInterval(interval); interval = null; }
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else { void refresh(); start(); }
    };
    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refresh]);

  const { platform, acquisition, marketplace, engagement, outcomes, funnel, alerts } = data;

  // Priority inbox — every row is sourced from the SAME definition as its
  // destination page (shared backend counts), and links to where the work
  // actually happens: staged import rows → the approval queue, guardrail /
  // pipeline flags → /admin/review, normalization flags → the credentials
  // queue.
  const guardrailFlags = alerts.review_items_by_type?.chat_guardrail ?? 0;
  const otherReviewItems = (alerts.review_items_pending ?? 0) - guardrailFlags;
  const priorityRows = [
    alerts.import_batches_pending > 0 && {
      icon: FileText,
      title: `${alerts.import_jobs_pending.toLocaleString()} imported ${alerts.import_jobs_pending === 1 ? "job" : "jobs"} awaiting review`,
      count: alerts.import_batches_pending,
      sub: `Across ${alerts.import_batches_pending} ${alerts.import_batches_pending === 1 ? "batch" : "batches"} (submitted and careers-page pulls)`,
      href: "/admin/job-imports",
    },
    guardrailFlags > 0 && {
      icon: ClipboardCheck,
      title: `${guardrailFlags} chat guardrail ${guardrailFlags === 1 ? "flag" : "flags"} to review`,
      count: guardrailFlags,
      sub: "What the assistant tried to say, caught by the deterministic guard",
      href: "/admin/review",
    },
    otherReviewItems > 0 && {
      icon: ClipboardCheck,
      title: `${otherReviewItems} pipeline ${otherReviewItems === 1 ? "flag" : "flags"} awaiting a decision`,
      count: otherReviewItems,
      sub: "Extraction, taxonomy, and link-check flags in the review feed",
      href: "/admin/review",
    },
    alerts.review_queue > 0 && {
      icon: ClipboardCheck,
      title: "Credentials flagged for normalization review",
      count: alerts.review_queue,
      href: "/admin/credentials#queue",
    },
    alerts.sla_breaches > 0 && {
      icon: Clock,
      title: "Applications waiting 5+ days for an employer response",
      count: alerts.sla_breaches,
      href: "#response-sla", // the nudge list at the bottom of this page
    },
    alerts.unmatched_learners > 0 && {
      icon: Users,
      title: "Onboarded applicants with no eligible matches",
      count: alerts.unmatched_learners,
      href: "/admin/applicants",
    },
    alerts.verified_not_sharing > 0 && {
      icon: Users,
      title: "Verified workers not yet discoverable (no sharing consent)",
      count: alerts.verified_not_sharing,
      href: "/admin/applicants",
    },
  ].filter(Boolean).slice(0, 6) as {
    icon: React.ElementType; title: string; count: number; href: string; sub?: string;
  }[];

  return (
    <main className="py-8">
      <div className="page-shell space-y-10">
        <TourWelcomeBand />
        <PageHeader
          eyebrow="Admin console"
          title="Command center"
          lead="Where the marketplace stands today, what needs your attention, and where to act."
          actions={
            <div className="flex items-center gap-2 text-caption text-slate-muted" data-tour-id="admin-refresh">
              {cmdKHintVisible && (
                <div className="inline-flex items-center gap-2 rounded-full border border-hairline bg-white px-3 py-1 text-caption text-slate">
                  <span>Tip: press <kbd className="rounded-xs border border-hairline bg-stone/40 px-1 text-micro">⌘K</kbd> to jump anywhere</span>
                  <button
                    onClick={dismissCmdKHint}
                    aria-label="Dismiss tip"
                    className="rounded-full p-0.5 text-slate-muted transition-colors hover:text-cohere-ink"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              )}
              {lastUpdated && (
                <span className="tabular-nums">Updated {lastUpdated.toLocaleTimeString()}</span>
              )}
              <button
                onClick={() => { void refresh(); }}
                disabled={refreshing}
                className="inline-flex items-center gap-1 rounded-full border border-hairline bg-white px-3 py-1 text-caption text-cohere-ink transition-colors hover:border-cohere-ink disabled:opacity-50"
                title="Refresh"
              >
                {refreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                Refresh
              </button>
              <RecomputeButton token={token} />
            </div>
          }
        />

        {/* 1 — Priority inbox: what needs your attention, first. Replaces both the
             pending-items banner and the older "Needs attention" alert grid so
             admins see one clear action list on first run. */}
        <section className="space-y-3" data-tour-id="admin-priority">
          <h2 className="text-subhead font-medium text-cohere-ink">Needs your attention</h2>
          {priorityRows.length === 0 ? (
            <div className="flex items-center gap-3 rounded-md border border-hairline bg-white p-6">
              <CheckCircle2 className="h-5 w-5 text-cohere-green" strokeWidth={1.75} />
              <p className="text-body text-cohere-ink">You&apos;re all caught up ✓</p>
            </div>
          ) : (
            <ul className="divide-y divide-hairline rounded-md border border-hairline bg-white overflow-hidden">
              {priorityRows.map((row) => (
                <li key={row.title}>
                  <Link
                    href={row.href}
                    className="group flex items-center gap-4 p-6 transition-colors hover:bg-parchment/40"
                  >
                    <row.icon className="h-4 w-4 shrink-0 text-slate-muted" strokeWidth={1.75} aria-hidden />
                    <div className="min-w-0 flex-1">
                      <p className="text-body text-cohere-ink">{row.title}</p>
                      <p className="mt-0.5 text-caption text-slate">
                        {row.sub ?? `${row.count.toLocaleString()} ${row.count === 1 ? "item" : "items"} pending`}
                      </p>
                    </div>
                    <ChevronRight
                      className="h-4 w-4 shrink-0 text-slate-muted transition-transform group-hover:translate-x-0.5 group-hover:text-cohere-ink"
                      strokeWidth={1.75}
                    />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* 2 — At a glance: the always-visible KPIs and platform trends. */}
        <div className="space-y-4" data-tour-id="admin-glance">
          <h2 className="text-subhead font-medium text-cohere-ink">At a glance</h2>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <Metric label="Workers" value={n(platform.applicants)} sub={`+${n(acquisition.new_applicants_30d)} in 30 days`} href="/admin/applicants" />
          {/* Canonical job count = active postings. Filtered views elsewhere
              must carry a qualifier ("372 with locations" on the map). */}
          <Metric label="Open jobs" value={n(marketplace.active_jobs)} sub={`active postings · ${marketplace.top_trades.length} trades`} href="/admin/map?status=active" />
          <Metric label="Employers" value={n(platform.employers)} href="/admin/employers" />
          <Metric label="Eligible matches" value={n(data.matching.eligible)} sub={`${n(data.matching.applicants_matched)} of ${n(platform.applicants)} workers matched`} href="/admin/test-matches" />
          <Metric label="Placements" value={n(outcomes.placements)} sub={outcomes.median_wage ? `$${outcomes.median_wage.toLocaleString()} median wage` : undefined} href="/admin/foundation" />
          </div>
        </div>

        {/* 3 — Marketplace journey (the conversion story). The takeaway names
             the single worst stage transition so the chart drives an action
             (fix THAT stage) instead of just sitting there. */}
        <div data-tour-id="admin-funnel">
        <Section title="Marketplace funnel" hint="workers reaching each stage, cumulative">
          <div className="rounded-[10px] border border-hairline bg-white p-6">
            <MarketplaceFunnel stages={funnel} />
            {funnelTakeaway(funnel) && (
              <p className="mt-4 border-t border-hairline pt-3 text-caption text-slate">
                {funnelTakeaway(funnel)}
              </p>
            )}
          </div>
        </Section>
        </div>

        {/* 3b — Supply vs demand: where trained workers and open jobs miss
             each other, per trade. The diverging bars carry their own
             computed desert annotation. */}
        <SupplyDemandSection token={token} />

        {/* 4 — Jobs by trade + activity. (The old "Trust" metric trio was
             redundant: Verified and Discoverable are funnel stages above, and
             credentials in review already lead the priority inbox.) */}
        <div className="grid gap-8 lg:grid-cols-2">
          <Section title="Jobs by trade" hint={`${n(marketplace.active_jobs)} active jobs`}>
            <div className="rounded-[10px] border border-hairline bg-white p-5">
              <ShareBars items={marketplace.top_trades.map((t) => ({ label: t.name, value: t.count }))} />
              {marketplace.top_trades.length > 0 && marketplace.active_jobs > 0 && (
                <p className="mt-3 border-t border-hairline pt-3 text-caption text-slate">
                  {marketplace.top_trades[0].name} leads with {n(marketplace.top_trades[0].count)} of{" "}
                  {n(marketplace.active_jobs)} active jobs ({Math.round((marketplace.top_trades[0].count / marketplace.active_jobs) * 100)}%).
                </p>
              )}
            </div>
          </Section>
          <Section title="Activity" hint="all-time, by type">
            <div className="rounded-[10px] border border-hairline bg-white p-5">
              <ShareBars
                items={engagement.by_type.map((e) => ({ label: EVENT_LABELS[e.type] ?? e.type, value: e.count }))}
                emptyLabel="No engagement recorded yet. Activity appears once workers or employers act."
              />
              {engagement.total > 0 && (
                <p className="mt-3 border-t border-hairline pt-3 text-caption text-slate">
                  {engagement.total_7d > 0 ? (
                    <>
                      {n(engagement.total_7d)} events this week from{" "}
                      {n(engagement.active_applicants_7d + engagement.active_employers_7d)}{" "}
                      {engagement.active_applicants_7d + engagement.active_employers_7d === 1 ? "person" : "people"} ·{" "}
                      {n(engagement.total)} all-time.
                    </>
                  ) : (
                    <>
                      No activity in the past 7 days. All {n(engagement.total)} events come from{" "}
                      {n(engagement.active_applicants_total + engagement.active_employers_total)}{" "}
                      {engagement.active_applicants_total + engagement.active_employers_total === 1 ? "person" : "people"}, earlier.
                    </>
                  )}
                </p>
              )}
            </div>
          </Section>
        </div>

        <div id="response-sla" className="scroll-mt-24">
          <DormantApplicationsCard token={token} />
        </div>
      </div>
    </main>
  );
}

/**
 * Supply vs demand by trade — fetched client-side once; skeleton keeps the
 * loaded row shape, errors offer retry, and the empty state comes from the
 * component itself ("No supply or demand recorded yet.").
 */
function SupplyDemandSection({ token }: { token: string }) {
  const [data, setData] = useState<SupplyDemandResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    setData(null);
    fetchSupplyDemand(token)
      .then(setData)
      .catch(() => setError("Could not load supply and demand. The API may be unreachable."));
  }, [token]);
  useEffect(() => {
    load();
  }, [load]);

  return (
    <Section
      title="Supply vs demand by trade"
      hint={
        data
          ? `${n(data.total_workers)} workers · ${n(data.total_jobs)} open jobs`
          : undefined
      }
    >
      <div className="rounded-[10px] border border-hairline bg-white p-6">
        {error ? (
          <div>
            <p className="text-body text-cohere-ink">{error}</p>
            <button
              type="button"
              onClick={load}
              className="mt-3 rounded-full border border-hairline bg-white px-4 py-1.5 text-caption text-cohere-ink transition-colors hover:border-cohere-ink"
            >
              Try again
            </button>
          </div>
        ) : data ? (
          <SupplyDemandBars families={data.families} />
        ) : (
          <div aria-busy="true" aria-label="Loading supply and demand">
            <div className="h-3 w-full border-b border-hairline pb-1.5" />
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className={`grid grid-cols-[minmax(96px,150px)_1fr_1fr] items-center gap-x-3 py-2 ${i > 0 ? "border-t border-hairline" : ""}`}
              >
                <div className="h-3.5 w-24 rounded-full bg-stone" />
                <div className="flex justify-end">
                  <div className="h-[10px] rounded-l-full bg-stone" style={{ width: `${65 - i * 7}%` }} />
                </div>
                <div className="h-[10px] rounded-r-full bg-stone" style={{ width: `${25 + i * 5}%` }} />
              </div>
            ))}
          </div>
        )}
      </div>
    </Section>
  );
}

/**
 * Recompute with the shared confirm→progress→error pattern (same behavior
 * as matching-config activation): a confirm dialog states the scope, then
 * the button polls /admin/matching/recompute-status until the run completes
 * and surfaces recompute_runs.error instead of silently resetting.
 */
function RecomputeButton({ token }: { token: string }) {
  const [confirming, setConfirming] = useState(false);
  const [state, setState] = useState<"idle" | "starting" | "running">("idle");
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    if (state !== "running") return;
    let cancelled = false;
    const poll = async () => {
      try {
        const s = await fetchRecomputeStatus(token);
        if (cancelled) return;
        setElapsed(s.run?.elapsed_seconds ?? null);
        if (s.run?.status === "failed") {
          setRunError(s.run.error || "Recompute failed. Check the worker logs.");
          setState("idle");
        } else if (s.run?.status === "complete") {
          setState("idle");
          setElapsed(null);
        }
      } catch { /* keep polling */ }
    };
    void poll();
    const iv = setInterval(poll, 4000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [state, token]);

  async function kick() {
    setState("starting");
    setRunError(null);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/admin/ops/recompute-matches`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error(String(res.status));
      setConfirming(false);
      setState("running");
    } catch {
      setRunError("Could not start the recompute. The API may be unreachable.");
      setConfirming(false);
      setState("idle");
    }
  }

  return (
    <>
      <button
        onClick={() => setConfirming(true)}
        disabled={state !== "idle"}
        className="inline-flex items-center gap-1 rounded-full border border-hairline bg-white px-3 py-1 text-caption text-cohere-ink transition-colors hover:border-cohere-ink disabled:opacity-60"
        title="Rescore every applicant against every job"
      >
        {state !== "idle" ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <RefreshCw className="h-3.5 w-3.5" />
        )}
        {state === "running"
          ? `Recomputing…${elapsed != null ? ` ${elapsed}s` : ""}`
          : "Recompute matches"}
      </button>
      {runError && (
        <span className="text-caption text-error-red" role="alert">{runError}</span>
      )}
      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        onConfirm={() => { void kick(); }}
        busy={state === "starting"}
        title="Recompute all matches?"
        confirmLabel="Start recompute"
        body={
          <p>
            This rescores <strong>every applicant against every active job</strong> with
            the current config. It runs in the background for a few minutes; scores and
            tiers update as it completes. Safe to run alongside the scheduled recompute,
            since overlapping runs are locked out.
          </p>
        }
      />
    </>
  );
}
