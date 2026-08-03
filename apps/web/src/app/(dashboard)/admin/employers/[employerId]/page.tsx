/**
 * Admin — Employer Detail Page
 *
 * Shows full employer profile: company info, contact, partner status,
 * and a table of all their jobs with applicant counts.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import {
  MapPin,
  Building2,
  Globe,
  MessageSquare,
  Briefcase,
  Users,
  ExternalLink,
} from "lucide-react";

import { fetchAdminEmployerDetail } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { Reveal, Stagger, StaggerItem, MonoLabel } from "@/components/ui";

interface PageProps {
  params: Promise<{ employerId: string }>;
}

function formatPay(
  min: number | null,
  max: number | null,
  type: string | null,
): string | null {
  if (min === null && max === null) return null;
  const suffix = type === "hourly" ? "/hr" : type === "salary" ? "/yr" : "";
  const fmt = (n: number) =>
    type === "salary"
      ? `$${(n / 1000).toFixed(0)}k`
      : `$${n.toFixed(0)}`;
  if (min !== null && max !== null) return `${fmt(min)}–${fmt(max)}${suffix}`;
  if (min !== null) return `${fmt(min)}+${suffix}`;
  return `Up to ${fmt(max!)}${suffix}`;
}

function formatWorkSetting(s: string | null) {
  if (!s) return null;
  return { on_site: "On-site", remote: "Remote", hybrid: "Hybrid" }[s] ?? s;
}

export default async function AdminEmployerDetailPage({ params }: PageProps) {
  const { employerId } = await params;

  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  let emp;
  try {
    emp = await fetchAdminEmployerDetail(employerId, session.access_token);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      return (
        <main className="py-8">
          <div className="page-shell">
            <BackLink />
            <div className="mt-6 bg-error-red/[0.06] border border-error-red/30 rounded-md p-5 text-body text-cohere-ink">
              Employer not found.
            </div>
          </div>
        </main>
      );
    }
    return (
      <main className="py-8">
        <div className="page-shell">
          <BackLink />
          <div className="mt-6 bg-error-red/[0.06] border border-error-red/30 rounded-md p-5 text-body text-cohere-ink">
            <strong>Could not reach the API.</strong> The backend may be starting up. Please refresh.
          </div>
        </div>
      </main>
    );
  }

  const location = [emp.city, emp.state].filter(Boolean).join(", ");
  const activeJobs = emp.jobs.filter((j) => j.is_active);
  const inactiveJobs = emp.jobs.filter((j) => !j.is_active);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <BackLink />

        {/* Company header — white sheet */}
        <Reveal as="section" className="rounded-[14px] border border-hairline bg-white p-7">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <MonoLabel className="mb-3 block text-slate-muted">Employer</MonoLabel>
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="font-display text-card text-ink">{emp.name}</h1>
                {emp.is_partner && (
                  <span className="inline-flex items-center text-caption font-medium text-white bg-ink rounded-sm px-2.5 py-1">
                    Partner
                    {emp.partner_since && (
                      <span className="text-micro text-white/70 ml-1">
                        since {emp.partner_since.slice(0, 4)}
                      </span>
                    )}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap gap-x-5 gap-y-1.5 mt-3 text-body text-slate">
                {location && (
                  <span className="flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5 text-slate-muted" /> {location}
                  </span>
                )}
                {emp.industry && (
                  <span className="flex items-center gap-1.5">
                    <Building2 className="w-3.5 h-3.5 text-slate-muted" /> {emp.industry}
                  </span>
                )}
                {emp.website && (
                  <a
                    href={emp.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-ink hover:underline transition-colors"
                  >
                    <Globe className="w-3.5 h-3.5" /> {emp.website.replace(/^https?:\/\//, "")}
                  </a>
                )}
              </div>

              {emp.description && (
                <p className="mt-4 text-body text-slate leading-relaxed">{emp.description}</p>
              )}
            </div>

            {/* Job stats */}
            <p className="shrink-0 text-right text-body text-slate">
              <span className="font-medium text-ink tabular-nums">{emp.active_jobs}</span> active
              <span className="mx-1.5 text-slate-muted">·</span>
              <span className="font-medium text-ink tabular-nums">{emp.total_jobs}</span> total jobs
            </p>
          </div>

          {/* Contact */}
          {emp.contact_email && (
            <div className="mt-5 pt-4 border-t border-hairline flex items-center gap-4">
              <span className="text-body text-slate">{emp.contact_email}</span>
              {/* TODO(task #145): route to admin platform-message compose. */}
              <a
                href={`mailto:${emp.contact_email}`}
                className="inline-flex items-center gap-1.5 text-body font-medium text-ink hover:underline transition-colors"
              >
                <MessageSquare className="w-3.5 h-3.5" /> Send message
              </a>
            </div>
          )}
        </Reveal>

        {/* Active jobs */}
        {activeJobs.length > 0 && (
          <section>
            <h2 className="text-feature font-display text-cohere-ink mb-3 flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-slate" />
              Active jobs
              <span className="text-caption font-normal text-slate">({activeJobs.length})</span>
            </h2>
            <Stagger className="space-y-2">
              {activeJobs.map((job) => (
                <StaggerItem key={job.id}>
                  <JobRow job={job} employerId={employerId} />
                </StaggerItem>
              ))}
            </Stagger>
          </section>
        )}

        {/* Inactive jobs (collapsed summary) */}
        {inactiveJobs.length > 0 && (
          <section>
            <h2 className="text-feature font-display text-slate mb-3 flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-slate" />
              Inactive / archived jobs
              <span className="text-caption font-normal text-slate">({inactiveJobs.length})</span>
            </h2>
            <Stagger className="space-y-2">
              {inactiveJobs.map((job) => (
                <StaggerItem key={job.id}>
                  <JobRow job={job} employerId={employerId} />
                </StaggerItem>
              ))}
            </Stagger>
          </section>
        )}

        {emp.jobs.length === 0 && (
          <div className="border border-border-light rounded-md bg-white p-8 text-center">
            <p className="text-slate text-body">No jobs posted yet.</p>
          </div>
        )}
      </div>
    </main>
  );
}

function BackLink() {
  return (
    <Link href="/admin/employers" className="btn-secondary">
      ← Back to employers
    </Link>
  );
}

function JobRow({
  job,
  employerId,
}: {
  job: {
    id: string;
    title: string;
    city: string | null;
    state: string | null;
    work_setting: string | null;
    experience_level: string | null;
    is_active: boolean;
    pay_min: number | null;
    pay_max: number | null;
    pay_type: string | null;
    source_url: string | null;
    eligible_count: number;
    near_fit_count: number;
    total_visible: number;
  };
  employerId: string;
}) {
  const location = [job.city, job.state].filter(Boolean).join(", ");
  const pay = formatPay(job.pay_min, job.pay_max, job.pay_type);
  const setting = formatWorkSetting(job.work_setting);

  return (
    <div className={`bg-white border rounded-md p-4 transition-colors hover:border-cohere-ink/25 ${job.is_active ? "border-border-light" : "border-border-light opacity-60"}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-body text-cohere-ink">{job.title}</span>
            {!job.is_active && (
              <span className="text-micro bg-stone text-slate-muted border border-hairline rounded-sm px-1.5 py-0.5">
                Inactive
              </span>
            )}
            {job.experience_level && (
              <span className="text-micro bg-stone text-slate border border-hairline rounded-sm px-1.5 py-0.5 capitalize">
                {job.experience_level}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5 text-caption text-slate">
            {location && <span>{location}</span>}
            {setting && <span>{setting}</span>}
            {pay && <span className="text-cohere-ink font-medium">{pay}</span>}
          </div>
        </div>

        {/* Applicant counts + actions */}
        <div className="shrink-0 flex items-center gap-4">
          <p className="text-caption text-slate whitespace-nowrap">
            <span className="font-medium text-cohere-ink tabular-nums">{job.eligible_count}</span> eligible
            <span className="mx-1 text-slate-muted">·</span>
            <span className="font-medium text-cohere-ink tabular-nums">{job.near_fit_count}</span> near fit
          </p>

          <div className="flex items-center gap-2 border-l border-hairline pl-4">
            <Link
              href={`/employer/jobs/${job.id}/applicants`}
              className="inline-flex items-center gap-1 text-micro font-medium text-cohere-blue hover:underline transition-colors"
            >
              <Users className="w-3.5 h-3.5" /> Matched candidates ({job.total_visible})
            </Link>
            {job.source_url && (
              <a
                href={job.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-micro text-slate-muted hover:text-slate transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
