/**
 * Employer dashboard — the day's queue, not a second jobs list.
 *
 * Shows:
 *   - Company summary (name, location, partner badge)
 *   - Applications waiting for review (the actual work queue)
 *   - Careers-page sync health (latest source status)
 *   - One-line jobs summary linking to the full jobs list
 *
 * The full jobs list (with filters and per-job candidate counts) lives at
 * /employer/jobs — the dashboard links there instead of duplicating it.
 *
 * Server component: fetches data server-side.
 */
import { Suspense } from "react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Plus, ChevronRight, Inbox, RefreshCw, Briefcase, CalendarClock } from "lucide-react";

import { fetchMyCompany } from "@/lib/api/employer";
import { listEmployerApplications } from "@/lib/api/transactions";
import { listSchedulingRequests } from "@/lib/api/team";
import { listCareerSources, type CareerSource } from "@/lib/api/careerSource";
import { ApiError } from "@/lib/api/client";
import { formatRelative } from "@/lib/time";
import { createClient } from "@/lib/supabase/server";
import { PageHeader, MonoLabel, Reveal } from "@/components/ui";
import { RouteLoading } from "@/components/ui/RouteLoading";
import { TourWelcomeBand } from "@/components/tour/TourWelcomeBand";

export default async function EmployerDashboard() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const role = user.app_metadata?.role;
  if (role === "admin") redirect("/admin/employers");
  if (role !== "employer") redirect("/login");

  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");

  // Stream: paint the route shell instantly while the day's queue loads.
  // Data fetching below is unchanged — only where it is awaited moved.
  return (
    <Suspense fallback={<RouteLoading variant="dashboard" headerActions />}>
      <EmployerHome token={session.access_token} />
    </Suspense>
  );
}

async function EmployerHome({ token }: { token: string }) {
  let apiError = false;
  let companyMissing = false;
  const [company, newApplications, sources, schedInbox] = await Promise.all([
    fetchMyCompany(token).catch((e) => {
      if (e instanceof ApiError && e.status === 404) { companyMissing = true; return null; }
      apiError = true; return null;
    }),
    listEmployerApplications(token, "submitted").catch(() => null),
    listCareerSources(token).catch(() => null),
    listSchedulingRequests(token).catch(() => null),
  ]);

  // No company linked but API is reachable → self-serve onboarding.
  // If the API is unreachable, fall through and show the legacy "contact admin"
  // message so we don't trap the user in a redirect loop.
  if (companyMissing && !apiError) {
    redirect("/employer/onboarding");
  }

  const queueCount = newApplications?.length ?? null;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <TourWelcomeBand />

        {/* Header — the ONE "New job" CTA on this page */}
        <PageHeader
          eyebrow="Employer workspace"
          title={company ? company.name : "Employer Dashboard"}
          lead={company ? "What needs your attention today." : undefined}
          actions={
            company ? (
              <Link href="/employer/jobs/new" className="btn-primary">
                <Plus className="w-4 h-4" /> New job
              </Link>
            ) : undefined
          }
        />

        {/* API unreachable fallback — only shown when we couldn't verify company state. */}
        {!company && (
          <Reveal className="rounded-md border border-cohere-coral-soft bg-cohere-coral/10 p-5 text-body text-cohere-ink">
            <strong className="font-medium">We couldn&apos;t reach the SKILLED service.</strong>{" "}
            Refresh in a moment. If the issue continues, contact{" "}
            <a
              className="underline hover:text-cohere-blue"
              href="mailto:support@skilled-nation.org"
            >
              support@skilled-nation.org
            </a>
            .
          </Reveal>
        )}

        {/* Company summary */}
        {company && (
          <Reveal>
            <div className="rounded-[14px] border border-hairline bg-white p-7">
              <div className="flex items-center gap-3 mb-6">
                <span className="text-caption font-medium tracking-[0.04em] text-slate-muted">Company</span>
                {company.is_partner && (
                  <span className="inline-flex items-center rounded-pill bg-ink px-3 py-1 text-caption font-medium text-white">
                    Partner
                  </span>
                )}
              </div>
              <dl className="grid grid-cols-2 sm:grid-cols-3 gap-6">
                {company.industry && (
                  <div>
                    <dt className="text-micro font-medium tracking-wide text-slate-muted">Industry</dt>
                    <dd className="mt-1 text-body-lg text-ink">{company.industry}</dd>
                  </div>
                )}
                {(company.city || company.state) && (
                  <div>
                    <dt className="text-micro font-medium tracking-wide text-slate-muted">Location</dt>
                    <dd className="mt-1 text-body-lg text-ink">
                      {[company.city, company.state].filter(Boolean).join(", ")}
                    </dd>
                  </div>
                )}
                <div>
                  <dt className="text-micro font-medium tracking-wide text-slate-muted">Jobs</dt>
                  <dd className="mt-1 text-body-lg text-ink tabular-nums">
                    {company.total_jobs} total · {company.active_jobs} active
                  </dd>
                </div>
              </dl>
            </div>
          </Reveal>
        )}

        {/* Today — the queue and health lines the jobs list can't give you */}
        {company && (
          <section data-tour-id="employer-today">
            <MonoLabel className="mb-5 block">Today</MonoLabel>
            <div className="rounded-[10px] border border-hairline bg-white">
              {/* Applications waiting for review */}
              <Link
                href="/employer/applications"
                className="flex items-center justify-between gap-3 px-5 py-3.5 transition-colors hover:bg-stone/30"
              >
                <p className="text-body text-cohere-ink">
                  <Inbox className="mr-2 inline h-4 w-4 text-slate-muted" aria-hidden="true" />
                  {queueCount === null
                    ? "Applications: open the review queue"
                    : queueCount === 0
                      ? "No new applications waiting for review"
                      : (
                        <>
                          <span className="font-medium tabular-nums">{queueCount}</span>
                          {` new application${queueCount === 1 ? "" : "s"} waiting for review`}
                        </>
                      )}
                </p>
                <ChevronRight className="h-4 w-4 shrink-0 text-slate-muted" aria-hidden="true" />
              </Link>

              {/* Scheduling requests — interviews a teammate asked YOU to
                  pick times for. Only renders when there's real work. */}
              {(schedInbox?.assigned_to_me ?? []).map((req) => (
                <Link
                  key={req.id}
                  href={`/employer/applications/${req.application_id}`}
                  className="flex items-center justify-between gap-3 border-t border-hairline px-5 py-3.5 transition-colors hover:bg-stone/30"
                >
                  <p className="text-body text-cohere-ink">
                    <CalendarClock className="mr-2 inline h-4 w-4 text-slate-muted" aria-hidden="true" />
                    Propose interview times for{" "}
                    <span className="font-medium">{req.applicant_name || "an applicant"}</span>
                    {req.job_title ? ` (${req.job_title})` : ""}
                    {req.requester_name ? ` — asked by ${req.requester_name}` : ""}
                  </p>
                  <ChevronRight className="h-4 w-4 shrink-0 text-slate-muted" aria-hidden="true" />
                </Link>
              ))}
              {(schedInbox?.waiting_on_others ?? []).map((req) => (
                <Link
                  key={req.id}
                  href={`/employer/applications/${req.application_id}`}
                  className="flex items-center justify-between gap-3 border-t border-hairline px-5 py-3.5 transition-colors hover:bg-stone/30"
                >
                  <p className="text-body text-slate">
                    <CalendarClock className="mr-2 inline h-4 w-4 text-slate-muted" aria-hidden="true" />
                    Waiting on {req.assignee_name || "a teammate"} to propose times for{" "}
                    {req.applicant_name || "an applicant"}
                    {req.job_title ? ` (${req.job_title})` : ""}
                  </p>
                  <ChevronRight className="h-4 w-4 shrink-0 text-slate-muted" aria-hidden="true" />
                </Link>
              ))}

              {/* Careers-page sync health */}
              <Link
                href="/employer/jobs/imports"
                className="flex items-center justify-between gap-3 border-t border-hairline px-5 py-3.5 transition-colors hover:bg-stone/30"
              >
                <p className="text-body text-cohere-ink">
                  <RefreshCw className="mr-2 inline h-4 w-4 text-slate-muted" aria-hidden="true" />
                  {syncHealthLine(sources)}
                </p>
                <ChevronRight className="h-4 w-4 shrink-0 text-slate-muted" aria-hidden="true" />
              </Link>

              {/* Jobs — one line, the list itself lives on /employer/jobs */}
              <Link
                href="/employer/jobs"
                className="flex items-center justify-between gap-3 border-t border-hairline px-5 py-3.5 transition-colors hover:bg-stone/30"
              >
                <p className="text-body text-cohere-ink">
                  <Briefcase className="mr-2 inline h-4 w-4 text-slate-muted" aria-hidden="true" />
                  {company.total_jobs === 0
                    ? "No jobs yet. Post your first to start receiving ranked matches"
                    : (
                      <>
                        <span className="font-medium tabular-nums">{company.active_jobs}</span>
                        {` active job${company.active_jobs === 1 ? "" : "s"}. See matched candidates per job`}
                      </>
                    )}
                </p>
                <ChevronRight className="h-4 w-4 shrink-0 text-slate-muted" aria-hidden="true" />
              </Link>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** One human sentence describing the latest careers-page sync state. */
function syncHealthLine(sources: CareerSource[] | null): string {
  if (!sources || sources.length === 0) {
    return "No careers page connected. Connect one to keep your jobs synced";
  }
  // Most recently pulled source wins; fall back to the newest.
  const latest = [...sources].sort((a, b) =>
    (b.last_pulled_at ?? "").localeCompare(a.last_pulled_at ?? ""),
  )[0];
  const host = (() => {
    try { return new URL(latest.url).hostname; } catch { return latest.url; }
  })();
  if (!latest.last_pulled_at) {
    return `Careers page connected (${host}). First pull hasn't run yet`;
  }
  if (latest.last_status === "ok") {
    return `Careers page sync healthy: ${host} synced ${formatRelative(latest.last_pulled_at)}, ${latest.jobs_found} job${latest.jobs_found === 1 ? "" : "s"} on the site`;
  }
  return `Careers page sync needs attention: we couldn't connect to ${host}`;
}
