"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Users, Briefcase, Building2, Sparkles, ShieldCheck, KeyRound, RefreshCw,
  TrendingUp, MapPin, ClipboardCheck, CheckCircle2,
  Loader2, FileText, Clock, ChevronRight, X,
} from "lucide-react";
import { PageHeader } from "@/components/ui";
import { DormantApplicationsCard } from "@/components/admin/DormantApplicationsCard";
import { fetchAdminOverview, type PlatformOverview } from "@/lib/api/admin";

const n = (x: number | null | undefined) => (x === null || x === undefined ? "—" : x.toLocaleString());

const ACCENT_BG: Record<string, string> = {
  green: "border-cohere-green/25 bg-cohere-green text-white",
  navy: "border-cohere-navy/25 bg-cohere-navy text-white",
  coral: "border-studio-maroon/40 bg-cohere-coral text-white",
};

function Kpi({ label, value, sub, accent, href, icon: Icon }: {
  label: string; value: string; sub?: string; accent?: "green" | "navy" | "coral"; href?: string; icon?: React.ElementType;
}) {
  // Decapitalize ordinary Title-case labels so the phrase reads naturally
  // ("337 workers"), but leave brand/acronym labels ("SKILLED ID lookups") alone.
  const phrase = /^[A-Z][a-z]/.test(label) ? label.charAt(0).toLowerCase() + label.slice(1) : label;
  const inner = (
    <div className={`group h-full rounded-xl border p-5 transition-shadow ${
      accent ? ACCENT_BG[accent]
        : "border-hairline bg-white shadow-[0_1px_2px_rgba(12,10,9,0.04)] hover:shadow-[0_8px_28px_-12px_rgba(12,10,9,0.12)]"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className={`font-display text-[34px] leading-none tabular-nums ${accent ? "text-white" : "text-cohere-ink"}`}>{value}</span>
          <span className={`text-body font-medium ${accent ? "text-white/85" : "text-slate"}`}>{phrase}</span>
        </div>
        {Icon && <Icon className={`h-4 w-4 shrink-0 ${accent ? "text-white/70" : "text-slate-muted"}`} strokeWidth={1.5} aria-hidden />}
      </div>
      {sub && <div className={`mt-2 text-caption ${accent ? "text-white/65" : "text-slate-muted"}`}>{sub}</div>}
    </div>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
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

function BarList({ items, tone }: { items: { label: string; value: number }[]; tone: "green" | "blue" }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  const bar = tone === "green" ? "bg-cohere-green/70" : "bg-cohere-blue/70";
  return (
    <div className="rounded-xl border border-hairline bg-white p-5">
      <ul className="divide-y divide-hairline">
        {items.length === 0 && <li className="py-2 text-caption text-slate">No activity yet.</li>}
        {items.map((it) => (
          <li key={it.label} className="grid grid-cols-[1fr_auto] items-center gap-4 py-2.5">
            <div className="min-w-0">
              <div className="truncate text-body text-cohere-ink">{it.label}</div>
              <div className="mt-1.5 h-[3px] w-full overflow-hidden rounded-full bg-stone/70">
                <div className={`h-full ${bar}`} style={{ width: `${(it.value / max) * 100}%` }} />
              </div>
            </div>
            <span className="text-caption tabular-nums text-slate">{it.value.toLocaleString()}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const EVENT_LABELS: Record<string, string> = {
  interest_set: "Interest set", apply_click: "Apply clicks", dm_sent: "Messages sent",
  outreach_sent: "Employer outreach", hire_reported: "Hires reported", candidate_verified: "Candidate verifications",
};

export function AdminOverviewClient({ data: initialData, token }: { data: PlatformOverview; token: string }) {
  // Auto-poll every 30s so KPIs don't go stale after ingest / imports.
  // Pauses when the tab is hidden and resumes on focus.
  const [data, setData] = useState<PlatformOverview>(initialData);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
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

  const { platform, acquisition, verification, marketplace, engagement, outcomes, skilled_id, sync, funnel, alerts } = data;

  // Priority inbox — first-run-friendly view: only pending action buckets,
  // ranked by urgency, capped at 5 rows. Zero-count buckets are skipped entirely.
  // Replaces the earlier "Needs attention" alert grid + Pending items banner so
  // admins see a single, unambiguous action list on load.
  const priorityRows = [
    alerts.review_queue > 0 && {
      icon: ClipboardCheck,
      title: "Credential ingest batches pending review",
      count: alerts.review_queue,
      href: "/admin/credentials",
    },
    alerts.jobs_no_candidates > 0 && {
      icon: FileText,
      title: "Job import batches awaiting approval",
      count: alerts.jobs_no_candidates,
      href: "/admin/job-imports",
    },
    alerts.unmatched_learners > 0 && {
      icon: Users,
      title: "Applicants with low-confidence flags",
      count: alerts.unmatched_learners,
      href: "/admin/applicants?flag=review",
    },
    alerts.sync_pending > 0 && {
      icon: RefreshCw,
      title: "Unresolved sync events",
      count: alerts.sync_pending,
      href: "/admin/sync",
    },
    alerts.verified_not_sharing > 0 && {
      icon: Clock,
      title: "SLA-breach alerts",
      count: alerts.verified_not_sharing,
      href: "/admin/analytics/engagement",
    },
  ].filter(Boolean).slice(0, 5) as {
    icon: React.ElementType; title: string; count: number; href: string;
  }[];

  const fMax = Math.max(1, ...funnel.map((s) => s.count));
  const learnerCount = funnel[0]?.count || 1;

  return (
    <main className="py-8">
      <div className="page-shell space-y-10">
        <PageHeader
          eyebrow="Admin console"
          title="Command center"
          lead="Where the marketplace stands today, what needs your attention, and where to act."
          actions={
            <div className="flex items-center gap-2 text-caption text-slate-muted">
              {cmdKHintVisible && (
                <div className="inline-flex items-center gap-2 rounded-full border border-studio-maroon/30 bg-studio-maroon/[0.08] px-3 py-1 text-caption text-studio-maroon">
                  <span>Tip: press <kbd className="rounded-xs border border-studio-maroon/30 bg-white/70 px-1 text-micro">⌘K</kbd> to jump anywhere</span>
                  <button
                    onClick={dismissCmdKHint}
                    aria-label="Dismiss tip"
                    className="rounded-full p-0.5 text-studio-maroon/70 transition-colors hover:text-studio-maroon"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              )}
              <span className="tabular-nums">Updated {lastUpdated.toLocaleTimeString()}</span>
              <button
                onClick={() => { void refresh(); }}
                disabled={refreshing}
                className="inline-flex items-center gap-1 rounded-full border border-hairline bg-white px-3 py-1 text-caption text-cohere-ink transition-colors hover:border-cohere-ink disabled:opacity-50"
                title="Refresh"
              >
                {refreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                Refresh
              </button>
            </div>
          }
        />

        {/* 1 — Priority inbox: what needs your attention, first. Replaces both the
             pending-items banner and the older "Needs attention" alert grid so
             admins see one clear action list on first run. */}
        <section className="space-y-3">
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
                    <div className="shrink-0 rounded-sm bg-stone p-2">
                      <row.icon className="h-4 w-4 text-cohere-ink" strokeWidth={1.75} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-body text-cohere-ink">{row.title}</p>
                      <p className="mt-0.5 text-caption text-slate">
                        {row.count.toLocaleString()} {row.count === 1 ? "item" : "items"} pending
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
        <div className="space-y-4">
          <h2 className="text-subhead font-medium text-cohere-ink">At a glance</h2>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <Kpi icon={Users} label="Workers" value={n(platform.applicants)} sub={`+${acquisition.new_applicants_30d} in 30 days`} accent="green" href="/admin/applicants" />
          <Kpi icon={Briefcase} label="Open jobs" value={n(marketplace.active_jobs)} sub={`${marketplace.top_trades.length} trades`} href="/admin/map?status=active" />
          <Kpi icon={Building2} label="Employers" value={n(platform.employers)} href="/admin/employers" />
          <Kpi icon={Sparkles} label="Eligible matches" value={n(data.matching.eligible)} sub={`${n(data.matching.applicants_matched)} workers matched`} accent="navy" href="/admin/test-matches" />
          <Kpi icon={TrendingUp} label="Placements" value={n(outcomes.placements)} sub={outcomes.median_wage ? `$${outcomes.median_wage.toLocaleString()} median wage` : undefined} accent="coral" href="/admin/foundation" />
          </div>
        </div>

        {/* 3 — Marketplace journey (the conversion story) */}
        <Section title="Marketplace journey" hint="share of workers reaching each stage">
          <div className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
            <ul className="space-y-4">
              {funnel.map((s, i) => {
                const share = Math.round((s.count / learnerCount) * 100);
                const prev = i > 0 ? funnel[i - 1].count : null;
                const retain = prev ? Math.round((s.count / Math.max(prev, 1)) * 100) : null;
                return (
                  <li key={s.key} className="flex items-center gap-4">
                    <span className="w-44 shrink-0 text-body text-cohere-ink">{s.label}</span>
                    <div className="relative h-7 flex-1 overflow-hidden rounded-md bg-stone">
                      <div className="h-full rounded-md bg-cohere-green/85" style={{ width: `${Math.max(2, (s.count / fMax) * 100)}%` }} />
                    </div>
                    <span className="w-16 shrink-0 text-right font-display text-[20px] tabular-nums text-cohere-ink">{s.count.toLocaleString()}</span>
                    <span className="w-28 shrink-0 text-right text-caption text-slate">
                      {share}% of workers{retain !== null && i > 0 ? `, ${retain}% kept` : ""}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </Section>

        {/* 4 — Trust + activity */}
        <div className="grid gap-8 lg:grid-cols-2">
          <Section title="Trust" hint={`${verification.verified_rate}% of credentials verified`}>
            <div className="grid grid-cols-3 gap-4">
              <Kpi label="Verified" value={n(verification.institution_verified + verification.skilled_verified)} />
              <Kpi label="In review" value={n(verification.needs_review)} />
              <Kpi label="Discoverable" value={n(marketplace.discoverable_workers)} accent="green" />
            </div>
            <div className="mt-4"><BarList tone="green" items={marketplace.top_trades.map((t) => ({ label: t.name, value: t.count }))} /></div>
          </Section>
          <Section title="Activity" hint={`${n(engagement.total_7d)} events this week`}>
            <BarList tone="blue" items={engagement.by_type.map((e) => ({ label: EVENT_LABELS[e.type] ?? e.type, value: e.count }))} />
          </Section>
        </div>

        {/* 5 — Systems */}
        <Section title="Systems">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi icon={KeyRound} label="Active API partners" value={n(skilled_id.active)} sub={`${n(skilled_id.queries_7d)} queries this week`} href="/admin/skilled-id" />
            <Kpi icon={ShieldCheck} label="SKILLED ID lookups" value={n(skilled_id.queries_total)} sub="all-time, metered" href="/admin/skilled-id" />
            <Kpi icon={RefreshCw} label="Sync applied" value={n(sync.inbox_applied)} sub={`${n(sync.outbox_unpublished)} pending relay`} href="/admin/sync" />
            <Kpi icon={MapPin} label="Engagement events" value={n(engagement.total)} sub="all-time" href="/admin/engagement" />
          </div>
        </Section>

        <DormantApplicationsCard token={token} />
      </div>
    </main>
  );
}
