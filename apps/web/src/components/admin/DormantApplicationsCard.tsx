"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Loader2, Bell, Check } from "lucide-react";

import { DormantApplication, SLASummary, getSLASummary, nudgeEmployer } from "@/lib/api/transactions";

/**
 * Admin dashboard card — flags applications where the employer hasn't clicked
 * "review" within N days (default 5). Nudge sends a notification to their
 * primary contact.
 */
export function DormantApplicationsCard({ token }: { token: string }) {
  const [summary, setSummary] = useState<SLASummary | null>(null);
  const [nudging, setNudging] = useState<string | null>(null);
  const [nudged, setNudged] = useState<Set<string>>(new Set());

  async function refresh() {
    try { setSummary(await getSLASummary(token)); } catch { /* silent */ }
  }
  useEffect(() => { refresh(); }, [token]);

  async function nudge(app: DormantApplication) {
    setNudging(app.application_id);
    try {
      await nudgeEmployer(token, app.application_id, `${app.employer_name}, applicants have been waiting ${app.days_dormant}+ days on ${app.job_title}.`);
      setNudged((prev) => new Set(prev).add(app.application_id));
    } finally { setNudging(null); }
  }

  if (summary === null) {
    return (
      <div className="rounded-xl border border-hairline bg-white p-5">
        <div className="flex items-center gap-2 text-caption text-slate">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading SLA…
        </div>
      </div>
    );
  }

  const items = summary.items;
  const isEmpty = items.length === 0;

  return (
    <section className="rounded-xl border border-hairline bg-white p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <AlertTriangle className={`h-5 w-5 ${isEmpty ? "text-cohere-green" : "text-studio-maroon"}`} strokeWidth={1.75} />
            <h3 className="text-[1.0625rem] font-medium text-cohere-ink">Response-time SLA</h3>
          </div>
          <p className="mt-1 text-caption text-slate">
            Applications employers haven't opened for {summary.threshold_days}+ days.
          </p>
        </div>
        <p className="text-body text-slate">
          <span className="font-medium text-cohere-ink tabular-nums">{summary.dormant_count}</span> dormant
          <span className="mx-1.5 text-slate-muted">·</span>
          <span className="font-medium text-cohere-ink tabular-nums">{summary.dormant_employers}</span> employer{summary.dormant_employers === 1 ? "" : "s"}
        </p>
      </div>

      {isEmpty ? (
        <p className="mt-6 text-body text-slate">Every employer has responded on time this week. Nice.</p>
      ) : (
        <ul className="mt-4 divide-y divide-hairline">
          {items.slice(0, 12).map((it) => (
            <li key={it.application_id} className="flex flex-wrap items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-cohere-ink">{it.employer_name || "Employer"}</span>
                  <span aria-hidden className="text-caption text-slate-muted">—</span>
                  <span className="text-caption text-slate truncate">{it.job_title}</span>
                </div>
                <div className="text-caption text-slate-muted">
                  {it.applicant_name}, waiting <strong className="text-studio-maroon">{it.days_dormant}d</strong>
                  {it.knockout_failed && <span className="ml-2 text-studio-maroon">(flagged)</span>}
                </div>
              </div>
              {nudged.has(it.application_id) ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-cohere-green bg-cohere-green px-2.5 py-0.5 text-micro text-white">
                  <Check className="h-3 w-3" /> Nudged
                </span>
              ) : (
                <button
                  onClick={() => nudge(it)}
                  disabled={nudging === it.application_id}
                  className="btn-pill-outline inline-flex items-center gap-1.5"
                >
                  {nudging === it.application_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Bell className="h-3.5 w-3.5" />}
                  Nudge employer
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
