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
  const [company, jobsList] = await Promise.all([
    fetchMyCompany(token).catch((e) => {
      if (e instanceof ApiError && e.status === 404) return null;
      apiError = true; return null;
    }),
    fetchMyJobs(token).catch(() => null),
  ]);

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-white">
            {company ? company.name : "Employer Dashboard"}
          </h1>
        </div>

        {/* No employer linked warning */}
        {!company && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 text-sm text-amber-400">
            <strong>Employer account not linked.</strong> Contact a SkillPointe
            admin to connect your account to a company.
          </div>
        )}

        {/* Company summary */}
        {company && (
          <section className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
            <div className="flex items-center gap-3 mb-4">
              <h2 className="font-semibold text-white">Company</h2>
              {company.is_partner && (
                <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-full px-2.5 py-1">
                  Partner
                </span>
              )}
            </div>
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              {company.industry && (
                <div>
                  <dt className="text-xs font-medium text-zinc-500 uppercase tracking-wide">Industry</dt>
                  <dd className="mt-0.5 text-white">{company.industry}</dd>
                </div>
              )}
              {(company.city || company.state) && (
                <div>
                  <dt className="text-xs font-medium text-zinc-500 uppercase tracking-wide">Location</dt>
                  <dd className="mt-0.5 text-white">
                    {[company.city, company.state].filter(Boolean).join(", ")}
                  </dd>
                </div>
              )}
              <div>
                <dt className="text-xs font-medium text-zinc-500 uppercase tracking-wide">Total jobs</dt>
                <dd className="mt-0.5 text-2xl font-bold text-cyan-400 leading-none">{company.total_jobs}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-zinc-500 uppercase tracking-wide">Active jobs</dt>
                <dd className="mt-0.5 text-2xl font-bold text-cyan-400 leading-none">{company.active_jobs}</dd>
              </div>
            </dl>
          </section>
        )}

        {/* Jobs section */}
        {company && (
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-white">Your jobs</h2>
              <Link
                href="/employer/jobs/new"
                className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-300 border border-zinc-700 rounded-full px-3 py-1.5 hover:border-zinc-500 hover:text-white transition-colors"
              >
                <Plus className="w-3.5 h-3.5" /> New job
              </Link>
            </div>

            {!jobsList || jobsList.jobs.length === 0 ? (
              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center">
                <p className="text-zinc-300 font-medium">No jobs yet</p>
                <p className="text-sm text-zinc-500 mt-2">
                  Create your first job posting to start receiving ranked applicant matches.
                </p>
                <Link
                  href="/employer/jobs/new"
                  className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-cyan-400 hover:text-cyan-300 transition-colors"
                >
                  Create a job <ChevronRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            ) : (
              <div className="space-y-3">
                {jobsList.jobs.map((job) => (
                  <JobCard key={job.job_id} job={job} />
                ))}
              </div>
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
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 hover:border-zinc-700 transition-all">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-white truncate">{job.title}</h3>
            {!job.is_active && (
              <span className="text-xs text-zinc-500 bg-zinc-800 border border-zinc-700 rounded-full px-1.5 py-0.5 shrink-0">
                Inactive
              </span>
            )}
          </div>
          <p className="text-sm text-zinc-400 mt-0.5">
            {locationStr || "Location not set"}
            {job.work_setting && ` · ${formatWorkSetting(job.work_setting)}`}
          </p>
        </div>

        {/* Applicant counts */}
        <div className="shrink-0 flex gap-4 text-right">
          <div>
            <div className="text-xl font-bold text-emerald-400 leading-none">{job.eligible_count}</div>
            <div className="text-xs text-zinc-500 mt-0.5">eligible</div>
          </div>
          <div>
            <div className="text-xl font-bold text-amber-400 leading-none">{job.near_fit_count}</div>
            <div className="text-xs text-zinc-500 mt-0.5">near fit</div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-4 mt-4 pt-3 border-t border-zinc-800">
        <Link
          href={`/employer/jobs/${job.job_id}/applicants`}
          className="inline-flex items-center gap-1 text-sm font-medium text-cyan-400 hover:text-cyan-300 transition-colors"
        >
          <Users className="w-3.5 h-3.5" /> View matched candidates ({job.total_visible})
        </Link>
        <Link
          href={`/employer/jobs/${job.job_id}/edit`}
          className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <Edit3 className="w-3.5 h-3.5" /> Edit
        </Link>
      </div>
    </div>
  );
}
