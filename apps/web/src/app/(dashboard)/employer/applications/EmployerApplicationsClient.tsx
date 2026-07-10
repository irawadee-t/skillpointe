"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Loader2, ShieldAlert, Clock, Sparkles } from "lucide-react";

import { Application, listEmployerApplications } from "@/lib/api/transactions";
import { PageHeader } from "@/components/ui";

/**
 * Employer inbox — pipeline view of all applications across the employer's jobs.
 * Grouped by stage so the flow reads left-to-right (submitted → reviewed → interviewing → decided).
 */
export function EmployerApplicationsClient({ token }: { token: string }) {
  const [apps, setApps] = useState<Application[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [active, setActive] = useState<string>("all");

  useEffect(() => {
    listEmployerApplications(token).then(setApps).catch((e: Error) => setErr(e.message));
  }, [token]);

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

  const filtered =
    active === "all" ? apps ?? [] :
    active === "flagged" ? (apps ?? []).filter((a) => a.knockout_failed) :
    active === "dormant" ? (apps ?? []).filter((a) => !a.employer_viewed_at && a.days_since_submitted >= 5) :
    (apps ?? []).filter((a) => a.status === active);

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
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <BucketCard label="New" count={buckets.new.length}   active={active === "submitted"}    onClick={() => setActive("submitted")} />
            <BucketCard label="In review"  count={buckets.review.length}    active={active === "reviewed"}  onClick={() => setActive("reviewed")} />
            <BucketCard label="Interview"  count={buckets.interview.length} active={active === "interviewing"} onClick={() => setActive("interviewing")} />
            <BucketCard label="Decided"    count={buckets.decided.length}   active={active === "hired"}   onClick={() => setActive("hired")} />
          </div>
        )}

        {/* Filter chips */}
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
                    ? "border-cohere-ink bg-studio-dark-cork text-canvas"
                    : "border-hairline bg-white text-slate hover:border-cohere-ink hover:text-cohere-ink"
                }`}>
                {t.label}
              </button>
            ))}
          </div>
        )}

        {apps?.length === 0 && (
          <div className="rounded-xl border border-dashed border-hairline bg-white p-10 text-center">
            <p className="font-display text-feature text-cohere-ink">Nothing to review yet.</p>
            <p className="mt-1 text-body text-slate">Applications land here the moment a worker sends one.</p>
          </div>
        )}

        {filtered.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-hairline bg-white shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
            <table className="w-full text-body">
              <thead className="border-b border-hairline bg-stone/40">
                <tr>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Applicant</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Job</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Submitted</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {filtered.map((a) => {
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
                      <td className="px-4 py-3 text-caption text-slate">{a.job_title}</td>
                      <td className="px-4 py-3 text-caption text-slate">
                        {new Date(a.submitted_at).toLocaleDateString()}
                        {dormant && <div className="mt-0.5 inline-flex items-center gap-1 text-micro text-studio-maroon"><Clock className="h-3 w-3" /> {a.days_since_submitted}d — needs review</div>}
                      </td>
                      <td className="px-4 py-3"><StatusChip status={a.status} /></td>
                      <td className="px-4 py-3 text-right">
                        <Link href={`/employer/applications/${a.id}`} className="text-caption text-cohere-blue underline">Review</Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}

function BucketCard({ label, count, active, onClick }: { label: string; count: number; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`rounded-xl border p-4 text-left transition-shadow ${active ? "border-cohere-ink shadow-[0_4px_16px_-8px_rgba(12,10,9,0.16)]" : "border-hairline hover:border-cohere-ink/40"}`}>
      <div className="mono-label">{label}</div>
      <div className="mt-1 font-display text-heading text-cohere-ink">{count}</div>
    </button>
  );
}

function StatusChip({ status }: { status: Application["status"] }) {
  const m: Record<string, { label: string; tone: string }> = {
    submitted:    { label: "New",          tone: "border-studio-maroon/30 bg-studio-maroon/[0.06] text-studio-maroon" },
    reviewed:     { label: "In review",    tone: "border-cohere-blue/30 bg-wash-blue text-cohere-blue" },
    shortlisted:  { label: "Shortlisted",  tone: "border-cohere-blue/30 bg-wash-blue text-cohere-blue font-medium" },
    interviewing: { label: "Interviewing", tone: "border-cohere-green/30 bg-wash-green text-cohere-green" },
    offered:      { label: "Offered",      tone: "border-cohere-green/30 bg-wash-green text-cohere-green" },
    hired:        { label: "Hired",        tone: "border-cohere-green/30 bg-wash-green text-cohere-green font-semibold" },
    rejected:     { label: "Rejected",     tone: "border-hairline bg-stone/40 text-slate-muted" },
    withdrawn:    { label: "Withdrawn",    tone: "border-hairline bg-stone/40 text-slate-muted" },
  };
  const s = m[status] ?? m.submitted;
  return <span className={`rounded-full border px-2.5 py-0.5 text-micro ${s.tone}`}>{s.label}</span>;
}
