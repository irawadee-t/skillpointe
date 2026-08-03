"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Send, Clock, Eye, CalendarCheck, Sparkles, CheckCheck, XCircle } from "lucide-react";

import { Application, listMyApplications } from "@/lib/api/transactions";
import { useAutoRevalidate } from "@/hooks/useAutoRevalidate";
import { formatDateShort } from "@/lib/format";
import { PageHeader } from "@/components/ui";
import {
  APPLICATION_STAGES,
  currentStageIndex,
  isClosedStatus,
} from "@/components/applications/stages";
import { ApplicationStatusChip } from "@/components/applications/ApplicationStatusChip";
import { CalendarSubscribeCard } from "@/components/interviews/CalendarSubscribeCard";

// Icons layered on top of the shared canonical stage model (stages.ts) —
// the model owns names/count/order for BOTH the list and detail timelines.
const STAGE_ICONS: Record<(typeof APPLICATION_STAGES)[number]["key"], typeof Send> = {
  submitted: Send,
  reviewed: Eye,
  shortlisted: Sparkles,
  interviewing: CalendarCheck,
  offered: CheckCheck,
  hired: CheckCheck,
};

export function MyApplicationsClient({ token }: { token: string }) {
  const [apps, setApps] = useState<Application[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    listMyApplications(token).then(setApps).catch((e: Error) => setErr(e.message));
  }, [token]);

  // Employer decisions (reviewed/shortlisted/interview proposals) land in this
  // list without a manual reload — same freshness pattern as the DM inbox.
  useAutoRevalidate(
    () => listMyApplications(token).then(setApps).catch(() => {}),
    { intervalMs: 30_000 },
  );

  // Hired is a WIN, not a closure — it gets its own positive group and never
  // sits under "Closed" or renders dimmed (statusTones: hired = positiveSolid).
  const active = apps?.filter((a) => !["hired", "rejected", "withdrawn"].includes(a.status)) ?? [];
  const hired = apps?.filter((a) => a.status === "hired") ?? [];
  const closed = apps?.filter((a) => ["rejected", "withdrawn"].includes(a.status)) ?? [];

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
          <div className="rounded-xl border border-dashed border-hairline bg-white p-10 text-center" data-tour-id="applications-list">
            <p className="text-[1.0625rem] font-medium text-cohere-ink">Nothing sent yet.</p>
            <p className="mt-1 text-body text-slate">Your ranked matches are the fastest way to find one worth sending.</p>
            <Link href="/applicant/matches" className="btn-primary mt-4 inline-flex items-center gap-1.5">
              See your matches
            </Link>
          </div>
        )}

        {active.length > 0 && (
          <section className="space-y-3" data-tour-id="applications-list">
            <h2 className="mono-label">Open</h2>
            <div className="space-y-3">
              {active.map((a) => <ApplicationRow key={a.id} app={a} />)}
            </div>
          </section>
        )}

        {hired.length > 0 && (
          <section className="space-y-3 pt-4">
            <h2 className="mono-label text-cohere-green">Hired</h2>
            <div className="space-y-3">
              {hired.map((a) => <ApplicationRow key={a.id} app={a} />)}
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

        {/* Quiet calendar piping — confirmed interviews sync to Google /
            Outlook / Apple Calendar via a personal ICS subscription URL. */}
        {apps !== null && apps.length > 0 && (
          <div className="pt-2" data-tour-id="applications-calendar">
            <CalendarSubscribeCard token={token} />
          </div>
        )}
      </div>
    </main>
  );
}

function ApplicationRow({ app, muted }: { app: Application; muted?: boolean }) {
  const isClosed = isClosedStatus(app.status);
  const isHired = app.status === "hired";
  const stageIx = Math.max(0, currentStageIndex(app.status));
  const Icon = isClosed
    ? XCircle
    : (STAGE_ICONS[APPLICATION_STAGES[stageIx]?.key] ?? Clock);
  const dormant = !isHired && !app.employer_viewed_at && app.days_since_submitted >= 5;
  return (
    <Link
      href={`/applicant/applications/${app.id}`}
      className={`block rounded-[14px] border bg-white p-6 transition-[color,background-color,border-color,box-shadow] duration-200 ease-cohere hover:shadow-float ${isHired ? "border-cohere-green/40" : "border-hairline"} ${muted ? "opacity-70" : ""}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Icon className={`h-4 w-4 ${isHired ? "text-cohere-green" : "text-slate-muted"}`} strokeWidth={1.75} />
            <h3 className="font-medium text-cohere-ink truncate">{app.job_title}</h3>
          </div>
          <p className="mt-0.5 text-caption text-slate">
            {app.employer_name ?? "Employer"}, applied {formatAgo(app.submitted_at)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {app.knockout_failed && (
            <span className="rounded-full border border-studio-maroon bg-studio-maroon px-2 py-0.5 text-[11px] font-medium text-white">
              Flagged
            </span>
          )}
          {dormant && (
            <>
              <span
                className="rounded-full border border-studio-maroon bg-studio-maroon px-2 py-0.5 text-[11px] font-medium text-white"
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
                className="rounded-full border border-hairline bg-white px-2 py-0.5 text-[11px] font-medium text-slate transition-colors hover:border-cohere-ink hover:text-cohere-ink"
              >
                Follow up
              </button>
            </>
          )}
          <ApplicationStatusChip status={app.status} />
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
              className="absolute left-3 top-1.5 h-0.5 bg-cohere-green transition-[width] duration-300 ease-cohere"
              style={{ width: `calc(${(stageIx / (APPLICATION_STAGES.length - 1)) * 100}% - 12px)` }}
              aria-hidden="true"
            />
          )}
          {APPLICATION_STAGES.map((s, i) => {
            const isDone = !isClosed && i < stageIx;
            const isCurrent = !isClosed && i === stageIx;
            return (
              <div key={s.key} className="relative z-10 flex flex-col items-center gap-1.5">
                <span
                  className={`h-3 w-3 rounded-full border-2 transition-colors ${
                    isClosed
                      ? "border-hairline bg-stone"
                      : isDone
                        ? "border-cohere-green bg-cohere-green"
                        : isCurrent
                          ? "border-cohere-green bg-white"
                          : "border-hairline bg-white"
                  }`}
                  aria-label={`${s.label}: ${isDone ? "done" : isCurrent ? "in progress" : "upcoming"}`}
                />
                <span
                  className={`text-[10px] font-medium leading-none ${
                    isCurrent
                      ? "text-cohere-green"
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
          {app.status === "rejected" ? "Closed. Not moving forward." : "Withdrawn."}
        </p>
      )}
    </Link>
  );
}

function formatAgo(iso: string): string {
  const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (d < 1)  return "today";
  if (d === 1) return "yesterday";
  if (d < 7)  return `${d}d ago`;
  return formatDateShort(iso); // shared formatter — "Jul 14" / "Jul 14, 2025"
}
