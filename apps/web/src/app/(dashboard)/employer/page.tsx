/**
 * Employer dashboard — Phase 6.2
 *
 * Shows:
 *   - Company summary (name, location, partner badge)
 *   - Quick stats (total jobs, active jobs)
 *   - Jobs list with per-job applicant counts
 *   - Links to ranked applicant views + job edit + new job
 *
 * Server component: fetches data server-side.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import {
  Plus,
  ChevronRight,
  Users,
  Edit3,
} from "lucide-react";

import { fetchMyCompany, fetchMyJobs, formatWorkSetting } from "@/lib/api/employer";
import type { EmployerJobSummary } from "@/lib/api/employer";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { PageHeader, Card, Chip, MonoLabel, Reveal, Stagger, StaggerItem } from "@/components/ui";

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

  const token = session.access_token;

  let apiError = false;
  let companyMissing = false;
  const [company, jobsList] = await Promise.all([
    fetchMyCompany(token).catch((e) => {
      if (e instanceof ApiError && e.status === 404) { companyMissing = true; return null; }
      apiError = true; return null;
    }),
    fetchMyJobs(token).catch(() => null),
  ]);

  // No company linked but API is reachable → self-serve onboarding.
  // If the API is unreachable, fall through and show the legacy "contact admin"
  // message so we don't trap the user in a redirect loop.
  if (companyMissing && !apiError) {
    redirect("/employer/onboarding");
  }

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        {/* Header */}
        <PageHeader
          eyebrow="Employer workspace"
          title={company ? company.name : "Employer Dashboard"}
          lead={company ? "Your jobs and the candidates ranked against them." : undefined}
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
            Refresh in a moment — if the issue continues, contact{" "}
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
            <div className="card-green p-7">
              <div className="flex items-center gap-3 mb-6">
                <span className="text-caption font-medium tracking-[0.04em] text-white/70">Company</span>
                {company.is_partner && (
                  <span className="inline-flex items-center rounded-pill bg-white/10 px-3 py-1 text-caption font-medium text-white">
                    Partner
                  </span>
                )}
              </div>
              <dl className="grid grid-cols-2 sm:grid-cols-4 gap-6">
                {company.industry && (
                  <div>
                    <dt className="text-micro font-medium tracking-wide text-white/70">Industry</dt>
                    <dd className="mt-1 text-body-lg text-white">{company.industry}</dd>
                  </div>
                )}
                {(company.city || company.state) && (
                  <div>
                    <dt className="text-micro font-medium tracking-wide text-white/70">Location</dt>
                    <dd className="mt-1 text-body-lg text-white">
                      {[company.city, company.state].filter(Boolean).join(", ")}
                    </dd>
                  </div>
                )}
                <div>
                  <dt className="text-micro font-medium tracking-wide text-white/70">Total jobs</dt>
                  <dd className="mt-1 font-display text-card leading-none text-white tabular-nums">{company.total_jobs}</dd>
                </div>
                <div>
                  <dt className="text-micro font-medium tracking-wide text-white/70">Active jobs</dt>
                  <dd className="mt-1 font-display text-card leading-none text-white tabular-nums">{company.active_jobs}</dd>
                </div>
              </dl>
            </div>
          </Reveal>
        )}

        {/* Jobs section */}
        {company && (
          <section>
            <div className="flex items-center justify-between mb-5">
              <MonoLabel>Your jobs</MonoLabel>
              <Link
                href="/employer/jobs/new"
                className="btn-pill-outline"
              >
                <Plus className="w-3.5 h-3.5" /> New job
              </Link>
            </div>

            {!jobsList || jobsList.jobs.length === 0 ? (
              <Card tone="stone" className="p-10 text-center">
                <p className="text-body-lg font-medium text-ink">No jobs yet</p>
                <p className="text-body text-slate mt-2">
                  Create your first job posting to start receiving ranked applicant matches.
                </p>
                <Link
                  href="/employer/jobs/new"
                  className="mt-4 inline-flex items-center gap-1.5 text-body font-medium text-cohere-blue hover:opacity-70 transition-opacity"
                >
                  Create a job <ChevronRight className="w-3.5 h-3.5" />
                </Link>
              </Card>
            ) : (
              <Stagger className="space-y-4">
                {jobsList.jobs.map((job) => (
                  <StaggerItem key={job.job_id}>
                    <JobCard job={job} />
                  </StaggerItem>
                ))}
              </Stagger>
            )}
          </section>
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function JobCard({ job }: { job: EmployerJobSummary }) {
  const locationStr = [job.city, job.state].filter(Boolean).join(", ");

  return (
    <Card className="p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-display text-feature text-cohere-ink truncate leading-tight">{job.title}</h3>
            {!job.is_active && (
              <Chip tone="neutral" size="sm" className="shrink-0">
                Inactive
              </Chip>
            )}
          </div>
          <p className="text-body text-slate mt-1">
            {locationStr || "Location not set"}
            {job.work_setting && `, ${formatWorkSetting(job.work_setting)}`}
          </p>
        </div>

        {/* Applicant counts */}
        <div className="shrink-0 flex flex-col items-end gap-1.5">
          <div className="card-green flex items-baseline gap-1.5 rounded-md px-4 py-2">
            <span className="font-display text-feature leading-none text-white tabular-nums">{job.eligible_count}</span>
            <span className="text-caption text-white/70">eligible</span>
          </div>
          <div className="flex items-baseline gap-1.5 rounded-md bg-stone px-4 py-2">
            <span className="font-display text-feature leading-none text-cohere-coral tabular-nums">{job.near_fit_count}</span>
            <span className="text-caption text-slate">near fit</span>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-5 mt-5 pt-4 border-t border-hairline">
        <Link
          href={`/employer/jobs/${job.job_id}/applicants`}
          className="inline-flex items-center gap-1.5 text-body font-medium text-cohere-blue hover:opacity-70 transition-opacity"
        >
          <Users className="w-3.5 h-3.5" /> View matched candidates ({job.total_visible})
        </Link>
        <Link
          href={`/employer/jobs/${job.job_id}/edit`}
          className="inline-flex items-center gap-1.5 text-body text-slate hover:text-ink transition-colors"
        >
          <Edit3 className="w-3.5 h-3.5" /> Edit
        </Link>
      </div>
    </Card>
  );
}
