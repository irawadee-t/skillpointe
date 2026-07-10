"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Send, Clock, Eye, CalendarCheck, Sparkles, CheckCheck, XCircle } from "lucide-react";

import { Application, listMyApplications } from "@/lib/api/transactions";
import { PageHeader } from "@/components/ui";

const STAGES: { key: Application["status"]; label: string; Icon: typeof Send }[] = [
  { key: "submitted",    label: "Submitted",    Icon: Send },
  { key: "reviewed",     label: "Reviewed",     Icon: Eye },
  { key: "shortlisted",  label: "Shortlisted",  Icon: Sparkles },
  { key: "interviewing", label: "Interviewing", Icon: CalendarCheck },
  { key: "offered",      label: "Offered",      Icon: CheckCheck },
  { key: "hired",        label: "Hired",        Icon: CheckCheck },
  { key: "rejected",     label: "Closed",       Icon: XCircle },
];

export function MyApplicationsClient({ token }: { token: string }) {
  const [apps, setApps] = useState<Application[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    listMyApplications(token).then(setApps).catch((e: Error) => setErr(e.message));
  }, [token]);

  const active = apps?.filter((a) => !["hired", "rejected", "withdrawn"].includes(a.status)) ?? [];
  const closed = apps?.filter((a) => ["hired", "rejected", "withdrawn"].includes(a.status)) ?? [];

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Applications"
          title="Your applications"
          lead="Every job you've sent through SKILLED. Watch status, answer interview times, and see when employers open your file."
        />

        {err && <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4">{err}</div>}
        {apps === null && !err && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}
        {apps?.length === 0 && (
          <div className="rounded-xl border border-dashed border-hairline bg-white p-10 text-center">
            <p className="font-display text-feature text-cohere-ink">Nothing sent yet.</p>
            <p className="mt-1 text-body text-slate">Your ranked matches are the fastest way to find one worth sending.</p>
            <Link href="/applicant/matches" className="btn-primary mt-4 inline-flex items-center gap-1.5">
              See your matches
            </Link>
          </div>
        )}

        {active.length > 0 && (
          <section className="space-y-3">
            <h2 className="mono-label">Open</h2>
            <div className="space-y-3">
              {active.map((a) => <ApplicationRow key={a.id} app={a} />)}
            </div>
          </section>
        )}

        {closed.length > 0 && (
          <section className="space-y-3 pt-4">
            <h2 className="mono-label">Closed</h2>
            <div className="space-y-2">
              {closed.map((a) => <ApplicationRow key={a.id} app={a} muted />)}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

function ApplicationRow({ app, muted }: { app: Application; muted?: boolean }) {
  const stageIx = Math.max(0, STAGES.findIndex((s) => s.key === app.status));
  const Icon = STAGES[stageIx]?.Icon ?? Clock;
  const dormant = !app.employer_viewed_at && app.days_since_submitted >= 5;
  const isClosed = ["rejected", "withdrawn"].includes(app.status);
  // Item 12: closed applications render the whole timeline muted-grey so they
  // read as "closed" rather than stopped mid-flow.
  const timelineDone = !isClosed;
  return (
    <Link
      href={`/applicant/applications/${app.id}`}
      className={`block rounded-xl border border-hairline bg-white p-4 shadow-[0_1px_2px_rgba(12,10,9,0.04)] transition-shadow hover:shadow-[0_6px_20px_-10px_rgba(12,10,9,0.14)] ${muted ? "opacity-70" : ""}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-slate-muted" strokeWidth={1.75} />
            <h3 className="font-medium text-cohere-ink truncate">{app.job_title}</h3>
          </div>
          <p className="mt-0.5 text-caption text-slate">
            {app.employer_name ?? "Employer"}, applied {formatAgo(app.submitted_at)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {app.knockout_failed && (
            <span className="rounded-full border border-studio-maroon/30 bg-studio-maroon/[0.06] px-2.5 py-0.5 text-micro font-medium text-studio-maroon">
              Flagged
            </span>
          )}
          {dormant && (
            <>
              <span
                className="rounded-full border border-studio-maroon/30 bg-studio-maroon/[0.06] px-2.5 py-0.5 text-micro font-medium text-studio-maroon"
                title={`No response from the employer in ${app.days_since_submitted} days`}
              >
                No response, {app.days_since_submitted}d
              </span>
              {/* Item 11: follow-up action next to the dormant flag. Intercepts
                  the row Link so the click routes to /messages instead. */}
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  const params = new URLSearchParams({
                    to_employer: app.employer_id ?? "",
                    application_id: app.id,
                    job_title: app.job_title,
                  });
                  window.location.href = `/applicant/messages?${params.toString()}`;
                }}
                className="rounded-full border border-hairline bg-white px-2.5 py-0.5 text-micro font-medium text-slate transition-colors hover:border-cohere-ink hover:text-cohere-ink"
              >
                Follow up
              </button>
            </>
          )}
          <StatusPill status={app.status} />
        </div>
      </div>

      {/* Timeline stepper — labeled stages with a connector rail.
          Each stage shows: filled circle (done) / ring (current) / hollow (upcoming).
          Labels sit BELOW the circles so the applicant can actually read them. */}
      <div className="mt-4">
        <div className="relative flex items-center justify-between">
          {/* Background rail */}
          <div className="absolute inset-x-3 top-1.5 h-0.5 bg-stone" aria-hidden="true" />
          {/* Progress rail — colored up to current stage */}
          {!isClosed && stageIx > 0 && (
            <div
              className="absolute left-3 top-1.5 h-0.5 bg-studio-forest transition-[width] duration-500"
              style={{ width: `calc(${(stageIx / (STAGES.length - 1)) * 100}% - 12px)` }}
              aria-hidden="true"
            />
          )}
          {STAGES.map((s, i) => {
            const isDone = !isClosed && i < stageIx;
            const isCurrent = !isClosed && i === stageIx;
            return (
              <div key={s.key} className="relative z-10 flex flex-col items-center gap-1.5">
                <span
                  className={`h-3 w-3 rounded-full border-2 transition-colors ${
                    isClosed
                      ? "border-hairline bg-stone"
                      : isDone
                        ? "border-studio-forest bg-studio-forest"
                        : isCurrent
                          ? "border-studio-forest bg-white"
                          : "border-hairline bg-white"
                  }`}
                  aria-label={`${s.label}: ${isDone ? "done" : isCurrent ? "in progress" : "upcoming"}`}
                />
                <span
                  className={`text-[10px] font-medium leading-none ${
                    isCurrent
                      ? "text-studio-forest"
                      : isDone
                        ? "text-cohere-ink"
                        : "text-slate-muted"
                  }`}
                >
                  {s.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      {isClosed && (
        <p className="mt-3 text-micro text-slate-muted">
          {app.status === "rejected" ? "Closed — not moving forward." : "Withdrawn."}
        </p>
      )}
    </Link>
  );
}

function StatusPill({ status }: { status: Application["status"] }) {
  const map: Record<Application["status"], { label: string; tone: string }> = {
    submitted:    { label: "Sent",         tone: "border-hairline text-slate bg-white" },
    reviewed:     { label: "Reviewed",     tone: "border-cohere-blue/30 text-cohere-blue bg-wash-blue" },
    shortlisted:  { label: "Shortlisted",  tone: "border-cohere-blue/30 text-cohere-blue bg-wash-blue" },
    interviewing: { label: "Interviewing", tone: "border-cohere-green/30 text-cohere-green bg-wash-green" },
    offered:      { label: "Offered",      tone: "border-cohere-green/30 text-cohere-green bg-wash-green" },
    hired:        { label: "Hired",        tone: "border-cohere-green/30 text-cohere-green bg-wash-green font-semibold" },
    rejected:     { label: "Closed",       tone: "border-hairline text-slate-muted bg-stone/40" },
    withdrawn:    { label: "Withdrawn",    tone: "border-hairline text-slate-muted bg-stone/40" },
  };
  const m = map[status] ?? map.submitted;
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-micro ${m.tone}`}>{m.label}</span>
  );
}

function formatAgo(iso: string): string {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (d < 1)  return "today";
  if (d === 1) return "yesterday";
  if (d < 7)  return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}
