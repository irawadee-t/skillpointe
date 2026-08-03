"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Loader2, ShieldAlert, Clock, ChevronDown } from "lucide-react";

import { Application, listEmployerApplications } from "@/lib/api/transactions";
import { useAutoRevalidate } from "@/hooks/useAutoRevalidate";
import { formatDateShort } from "@/lib/format";
import { fetchMyCompany, patchMyCompany } from "@/lib/api/employer";
import { PageHeader, SearchWithSuggestions, useToast } from "@/components/ui";
import type { SuggestionItem } from "@/lib/suggest";
import { cn } from "@/lib/utils";
import { ApplicationStatusChip } from "@/components/applications/ApplicationStatusChip";
import { CalendarSubscribeCard } from "@/components/interviews/CalendarSubscribeCard";

/** sessionStorage key for per-job card expansion (persists for the session). */
const EXPANDED_KEY = "employer-apps-expanded";

/** Most recent activity on an application — orders the job cards. */
function activityTs(a: Application): number {
  return Math.max(
    ...[a.submitted_at, a.reviewed_at, a.decision_at, a.employer_viewed_at]
      .filter((d): d is string => Boolean(d))
      .map((d) => new Date(d).getTime())
      .filter((n) => Number.isFinite(n)),
    0,
  );
}

/** "1 new · 2 in review · 1 shortlisted" — from the rows currently shown. */
const SUMMARY_ORDER: Array<[Application["status"], string]> = [
  ["submitted", "new"],
  ["reviewed", "in review"],
  ["shortlisted", "shortlisted"],
  ["interviewing", "interviewing"],
  ["offered", "offered"],
  ["hired", "hired"],
  ["rejected", "closed"],
  ["withdrawn", "withdrawn"],
];

function summarize(rows: Application[]): string {
  return SUMMARY_ORDER
    .map(([status, label]) => [rows.filter((r) => r.status === status).length, label] as const)
    .filter(([n]) => n > 0)
    .map(([n, label]) => `${n} ${label}`)
    .join(" · ");
}

interface JobGroup {
  jobId: string;
  jobTitle: string;
  rows: Application[];
  lastActivity: number;
}

/**
 * Employer inbox — one card PER JOB. Each card header shows the job title and
 * a live stage summary; expanding reveals that job's application rows. The
 * top stage tiles stay global; search + filter chips filter within groups
 * (a job card hides entirely when nothing in it matches).
 */
export function EmployerApplicationsClient({ token, isEmployer = true }: { token: string; isEmployer?: boolean }) {
  const [apps, setApps] = useState<Application[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [active, setActive] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    listEmployerApplications(token).then(setApps).catch((e: Error) => setErr(e.message));
  }, [token]);

  // New applications and withdrawals land in the inbox without a manual
  // reload — same 30s freshness pattern as the applicant side. Filters,
  // search, and expansion state are all derived, so a refresh never
  // disturbs what the employer is doing.
  useAutoRevalidate(
    () => listEmployerApplications(token).then(setApps).catch(() => {}),
    { intervalMs: 30_000 },
  );

  // Default expansion: jobs with NEW or in-review applications open, decided-
  // only jobs collapsed. A session's manual toggles win (sessionStorage).
  useEffect(() => {
    if (!apps) return;
    let stored: Record<string, boolean> = {};
    try { stored = JSON.parse(sessionStorage.getItem(EXPANDED_KEY) ?? "{}") as Record<string, boolean>; } catch { /* fresh */ }
    const hasActive = new Map<string, boolean>();
    for (const a of apps) {
      hasActive.set(
        a.job_id,
        (hasActive.get(a.job_id) ?? false) || a.status === "submitted" || a.status === "reviewed",
      );
    }
    const next: Record<string, boolean> = {};
    for (const [jobId, open] of hasActive) next[jobId] = stored[jobId] ?? open;
    setExpanded(next);
  }, [apps]);

  function toggleJob(jobId: string) {
    setExpanded((prev) => {
      const next = { ...prev, [jobId]: !prev[jobId] };
      try { sessionStorage.setItem(EXPANDED_KEY, JSON.stringify(next)); } catch { /* private mode */ }
      return next;
    });
  }

  const buckets = useMemo(() => {
    const b: Record<string, Application[]> = {
      new: [], review: [], interview: [], decided: [],
    };
    for (const a of apps ?? []) {
      if (["submitted"].includes(a.status)) b.new.push(a);
      else if (["reviewed","shortlisted"].includes(a.status)) b.review.push(a);
      else if (["interviewing","offered"].includes(a.status)) b.interview.push(a);
      else b.decided.push(a);
    }
    return b;
  }, [apps]);

  const bucketFiltered =
    active === "all" ? apps ?? [] :
    active === "flagged" ? (apps ?? []).filter((a) => a.knockout_failed) :
    active === "dormant" ? (apps ?? []).filter((a) => !a.employer_viewed_at && a.days_since_submitted >= 5) :
    (apps ?? []).filter((a) => a.status === active);

  // Live search — the cards narrow with every letter typed (in-memory).
  const q = search.trim().toLowerCase();
  const filtered = q
    ? bucketFiltered.filter(
        (a) =>
          (a.applicant_name ?? "").toLowerCase().includes(q) ||
          (a.job_title ?? "").toLowerCase().includes(q),
      )
    : bucketFiltered;

  // Suggestion dropdown, drawn from THIS employer's loaded applications only
  // (inherently isolated — no cross-tenant source exists here) and matched by
  // the exact predicate the live filter uses, so picking one narrows the
  // cards precisely as typing it would. Prefix matches rank first.
  const suggestLocal = (query: string): Promise<SuggestionItem[]> => {
    const needle = query.trim().toLowerCase();
    if (!needle) return Promise.resolve([]);
    const names = new Set<string>();
    const jobs = new Set<string>();
    for (const a of apps ?? []) {
      if ((a.applicant_name ?? "").toLowerCase().includes(needle)) names.add(a.applicant_name ?? "");
      if ((a.job_title ?? "").toLowerCase().includes(needle)) jobs.add(a.job_title);
    }
    names.delete("");
    jobs.delete("");
    const byPrefixThenAlpha = (x: string, y: string) =>
      Number(!x.toLowerCase().startsWith(needle)) - Number(!y.toLowerCase().startsWith(needle)) ||
      x.localeCompare(y);
    const nameItems: SuggestionItem[] = [...names].sort(byPrefixThenAlpha)
      .map((label) => ({ kind: "applicant", label }));
    const jobItems: SuggestionItem[] = [...jobs].sort(byPrefixThenAlpha)
      .map((label) => ({ kind: "job", label }));
    return Promise.resolve(
      [...nameItems.slice(0, jobItems.length > 0 ? 5 : 8), ...jobItems].slice(0, 8),
    );
  };

  // The card region fades in (~150ms, motion-safe) when the FILTERS change —
  // never on the 30s poll, which must not re-animate content.
  const filterKey = `${active}|${q}`;
  const firstFilterKey = useRef(filterKey);
  const filterChanged = useRef(false);
  if (filterKey !== firstFilterKey.current) filterChanged.current = true;
  const fadeOnFilter = filterChanged.current
    ? "animate-[fade-in_150ms_ease_both] motion-reduce:animate-none"
    : undefined;

  // One card per job, holding only the rows that survive the filters. Jobs
  // with zero matching rows disappear; jobs with zero applications never
  // appear at all (this is an inbox, not the jobs list). Most recent
  // application activity floats a job's card to the top.
  const groups = useMemo<JobGroup[]>(() => {
    const byJob = new Map<string, JobGroup>();
    for (const a of filtered) {
      let g = byJob.get(a.job_id);
      if (!g) {
        g = { jobId: a.job_id, jobTitle: a.job_title, rows: [], lastActivity: 0 };
        byJob.set(a.job_id, g);
      }
      g.rows.push(a);
      g.lastActivity = Math.max(g.lastActivity, activityTs(a));
    }
    return [...byJob.values()].sort((x, y) => y.lastActivity - x.lastActivity);
  }, [filtered]);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Employer"
          title="Applications"
          lead="Everyone who applied through SKILLED. Review, shortlist, and set interview times without leaving here."
        />

        {err && <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4">{err}</div>}
        {apps === null && !err && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}

        {/* Bucket header cards */}
        {apps && apps.length > 0 && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" data-tour-id="apps-buckets">
            <BucketCard label="New" count={buckets.new.length}   active={active === "submitted"}    onClick={() => setActive("submitted")} />
            <BucketCard label="In review"  count={buckets.review.length}    active={active === "reviewed"}  onClick={() => setActive("reviewed")} />
            <BucketCard label="Interview"  count={buckets.interview.length} active={active === "interviewing"} onClick={() => setActive("interviewing")} />
            <BucketCard label="Decided"    count={buckets.decided.length}   active={active === "hired"}   onClick={() => setActive("hired")} />
          </div>
        )}

        {/* Search + filter chips — as-you-type dropdown over this employer's
            own applicants and jobs; typing without picking still live-filters. */}
        {apps && apps.length > 0 && (
          <SearchWithSuggestions
            value={search}
            onChange={setSearch}
            onPick={(item) => setSearch(item.label)}
            fetchSuggestions={suggestLocal}
            placeholder="Search applicant or job…"
            className="max-w-sm"
          />
        )}
        {apps && apps.length > 0 && (
          <div className="flex flex-wrap gap-2 border-b border-hairline pb-3">
            {[
              { key: "all", label: "All" },
              { key: "flagged", label: "Flagged" },
              { key: "dormant", label: "Awaiting response" },
            ].map((t) => (
              <button key={t.key} onClick={() => setActive(t.key)}
                className={`rounded-full border px-3 py-1 text-caption transition-colors ${
                  active === t.key
                    ? "border-ink bg-ink text-white"
                    : "border-hairline bg-white text-slate hover:border-cohere-ink hover:text-cohere-ink"
                }`}>
                {t.label}
              </button>
            ))}
          </div>
        )}

        {apps?.length === 0 && (
          <div className="rounded-xl border border-dashed border-hairline bg-white p-10 text-center">
            <p className="text-[1.0625rem] font-medium text-cohere-ink">Nothing to review yet.</p>
            <p className="mt-1 text-body text-slate">Applications land here the moment a worker sends one.</p>
          </div>
        )}

        {apps && apps.length > 0 && filtered.length === 0 && (
          <div key={filterKey} className={fadeOnFilter}>
            <div className="rounded-xl border border-hairline bg-white p-8 text-center">
              <p className="text-body font-medium text-cohere-ink">
                {q ? <>No results for &ldquo;{search.trim()}&rdquo;</> : "No applications in this view."}
              </p>
            </div>
          </div>
        )}

        {/* One card per job — header expands/collapses that job's rows. */}
        {groups.length > 0 && (
          <div key={filterKey} className={cn("space-y-4", fadeOnFilter)} data-tour-id="apps-groups">
            {groups.map((g) => {
              const isOpen = expanded[g.jobId] ?? true;
              return (
                <section key={g.jobId} className="rounded-xl border border-hairline bg-white shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
                  <button
                    type="button"
                    onClick={() => toggleJob(g.jobId)}
                    aria-expanded={isOpen}
                    className="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left"
                  >
                    <div className="min-w-0">
                      <h2 className="truncate text-[1.0625rem] font-medium text-cohere-ink">{g.jobTitle}</h2>
                      <p className="mt-0.5 text-caption text-slate">{summarize(g.rows)}</p>
                    </div>
                    <ChevronDown
                      aria-hidden="true"
                      className={`h-4 w-4 shrink-0 text-slate transition-transform duration-200 motion-reduce:transition-none ${isOpen ? "rotate-180" : ""}`}
                    />
                  </button>
                  {/* Smooth height animation via the grid-rows 0fr→1fr trick;
                      instant under prefers-reduced-motion. */}
                  <div
                    className={`grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none ${
                      isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
                    }`}
                  >
                    <div className="overflow-hidden">
                      {/* overflow-x-auto: on narrow screens (375px) the rows
                          scroll horizontally inside the card so Status +
                          Review stay reachable — the page body never scrolls
                          sideways. */}
                      <div className="overflow-x-auto border-t border-hairline">
                        <table className="w-full min-w-[520px] text-body">
                          <thead className="border-b border-hairline bg-stone/40">
                            <tr>
                              <th className="px-4 py-3 text-left text-caption font-medium text-slate">Applicant</th>
                              <th className="px-4 py-3 text-left text-caption font-medium text-slate">Submitted</th>
                              <th className="px-4 py-3 text-left text-caption font-medium text-slate">Status</th>
                              <th className="px-4 py-3" />
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-hairline">
                            {g.rows.map((a) => {
                              const dormant = !a.employer_viewed_at && a.days_since_submitted >= 5;
                              return (
                                <tr key={a.id} className={a.knockout_failed ? "bg-studio-maroon/[0.04]" : ""}>
                                  <td className="px-4 py-3">
                                    <div className="flex items-center gap-2">
                                      <span className="font-medium text-cohere-ink">{a.applicant_name || "Unknown"}</span>
                                      {a.knockout_failed && (
                                        <span className="inline-flex items-center gap-0.5 text-micro text-studio-maroon"><ShieldAlert className="h-3 w-3" /> Flagged</span>
                                      )}
                                    </div>
                                  </td>
                                  <td className="px-4 py-3 text-caption text-slate">
                                    {formatDateShort(a.submitted_at)}
                                    {dormant && <div className="mt-0.5 inline-flex items-center gap-1 text-micro text-studio-maroon"><Clock className="h-3 w-3" /> {a.days_since_submitted}d · needs review</div>}
                                  </td>
                                  <td className="px-4 py-3"><ApplicationStatusChip status={a.status} viewer="employer" /></td>
                                  <td className="px-4 py-3 text-right">
                                    <Link href={`/employer/applications/${a.id}`} className="text-caption text-cohere-blue underline">Review</Link>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </section>
              );
            })}
          </div>
        )}

        {/* Quiet calendar piping — every confirmed interview on your jobs
            syncs to Google / Outlook / Apple Calendar via a personal ICS
            subscription URL. Employer-only: admin has no interview calendar. */}
        {isEmployer && (
          <div className="pt-2">
            <CalendarSubscribeCard token={token} />
          </div>
        )}

        {/* Quiet settings row — company-wide default lives at the bottom of
            the page, out of the queue's prime position. Employer-only: admin
            views this page read-only. */}
        {isEmployer && (
          <div className="border-t border-hairline pt-4">
            <InternalApplyDefaultRow token={token} />
          </div>
        )}
      </div>
    </main>
  );
}

/**
 * "Accept applications on SKILLED Nation for all jobs by default."
 * Per-job settings on the job form override this.
 */
function InternalApplyDefaultRow({ token }: { token: string }) {
  const toast = useToast();
  const [value, setValue] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchMyCompany(token)
      .then((c) => setValue(c.accepts_internal_applications_default))
      .catch(() => setValue(null));
  }, [token]);

  if (value === null) return null;

  async function toggle(next: boolean) {
    setValue(next); // optimistic
    setSaving(true);
    try {
      const fresh = await patchMyCompany(token, { accepts_internal_applications_default: next });
      setValue(fresh.accepts_internal_applications_default);
      toast.success(next
        ? "All jobs now accept applications on SKILLED Nation by default"
        : "Default off. Jobs opt in individually");
    } catch {
      setValue(!next); // revert
      toast.error("Could not save that setting");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-caption font-medium text-cohere-ink">Accept applications on SKILLED Nation for all jobs</p>
        <p className="mt-0.5 text-caption text-slate-muted">
          Company default. Each job can still turn this on or off on its own form.
        </p>
      </div>
      <label className="flex shrink-0 cursor-pointer items-center gap-2 pt-0.5">
        <input
          type="checkbox"
          checked={value}
          disabled={saving}
          onChange={(e) => toggle(e.target.checked)}
          className="h-4 w-4 accent-studio-maroon"
        />
        <span className="text-caption text-slate">{value ? "On" : "Off"}</span>
      </label>
    </div>
  );
}

function BucketCard({ label, count, active, onClick }: { label: string; count: number; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`rounded-[10px] border bg-white px-4 py-3 text-left text-body transition-colors ${active ? "border-cohere-ink text-cohere-ink" : "border-hairline text-slate hover:border-cohere-ink/40"}`}>
      <span className="font-medium text-cohere-ink tabular-nums">{count}</span> {label.toLowerCase()}
    </button>
  );
}

