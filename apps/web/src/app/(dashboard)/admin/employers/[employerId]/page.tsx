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
  Star,
  Globe,
  Mail,
  Briefcase,
  Users,
  ExternalLink,
} from "lucide-react";

import { fetchAdminEmployerDetail } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";

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
        <main className="p-6 md:p-8">
          <div className="max-w-4xl mx-auto">
            <BackLink />
            <div className="mt-6 bg-red-50 border border-red-200 rounded-xl p-5 text-sm text-red-800">
              Employer not found.
            </div>
          </div>
        </main>
      );
    }
    return (
      <main className="p-6 md:p-8">
        <div className="max-w-4xl mx-auto">
          <BackLink />
          <div className="mt-6 bg-red-50 border border-red-200 rounded-xl p-5 text-sm text-red-800">
            <strong>Could not reach the API.</strong> The backend may be starting up — please refresh.
          </div>
        </div>
      </main>
    );
  }

  const location = [emp.city, emp.state].filter(Boolean).join(", ");
  const activeJobs = emp.jobs.filter((j) => j.is_active);
  const inactiveJobs = emp.jobs.filter((j) => !j.is_active);

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-4xl mx-auto space-y-6">
        <BackLink />

        {/* Company header */}
        <section className="bg-white border border-gray-200 rounded-xl p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-2xl font-bold text-spf-navy">{emp.name}</h1>
                {emp.is_partner && (
                  <span className="inline-flex items-center gap-1 text-sm font-medium text-spf-orange bg-orange-50 border border-orange-200 rounded-md px-2.5 py-1">
                    <Star className="w-3.5 h-3.5 fill-spf-orange" /> Partner
                    {emp.partner_since && (
                      <span className="text-xs text-orange-400 ml-0.5">
                        since {emp.partner_since.slice(0, 4)}
                      </span>
                    )}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap gap-x-5 gap-y-1.5 mt-3 text-sm text-gray-500">
                {location && (
                  <span className="flex items-center gap-1.5">
                    <MapPin className="w-3.5 h-3.5 text-gray-400" /> {location}
                  </span>
                )}
                {emp.industry && (
                  <span className="flex items-center gap-1.5">
                    <Building2 className="w-3.5 h-3.5 text-gray-400" /> {emp.industry}
                  </span>
                )}
                {emp.website && (
                  <a
                    href={emp.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-blue-600 hover:underline"
                  >
                    <Globe className="w-3.5 h-3.5" /> {emp.website.replace(/^https?:\/\//, "")}
                  </a>
                )}
              </div>

              {emp.description && (
                <p className="mt-4 text-sm text-gray-600 leading-relaxed">{emp.description}</p>
              )}
            </div>

            {/* Job stats */}
            <div className="shrink-0 flex gap-4 text-right">
              <div>
                <div className="text-3xl font-bold text-green-700 leading-none">{emp.active_jobs}</div>
                <div className="text-xs text-gray-400 mt-0.5">active jobs</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-gray-700 leading-none">{emp.total_jobs}</div>
                <div className="text-xs text-gray-400 mt-0.5">total jobs</div>
              </div>
            </div>
          </div>

          {/* Contact */}
          {emp.contact_email && (
            <div className="mt-5 pt-4 border-t border-gray-100 flex items-center gap-4">
              <span className="text-sm text-gray-500 font-mono">{emp.contact_email}</span>
              <a
                href={`mailto:${emp.contact_email}`}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-spf-navy hover:text-spf-navy/80"
              >
                <Mail className="w-3.5 h-3.5" /> Send email
              </a>
            </div>
          )}
        </section>

        {/* Active jobs */}
        {activeJobs.length > 0 && (
          <section>
            <h2 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-gray-400" />
              Active jobs
              <span className="text-sm font-normal text-gray-400">({activeJobs.length})</span>
            </h2>
            <div className="space-y-2">
              {activeJobs.map((job) => (
                <JobRow key={job.id} job={job} employerId={employerId} />
              ))}
            </div>
          </section>
        )}

        {/* Inactive jobs (collapsed summary) */}
        {inactiveJobs.length > 0 && (
          <section>
            <h2 className="font-semibold text-gray-500 mb-3 flex items-center gap-2 text-sm">
              <Briefcase className="w-4 h-4 text-gray-300" />
              Inactive / archived jobs
              <span className="font-normal text-gray-400">({inactiveJobs.length})</span>
            </h2>
            <div className="space-y-2">
              {inactiveJobs.map((job) => (
                <JobRow key={job.id} job={job} employerId={employerId} />
              ))}
            </div>
          </section>
        )}

        {emp.jobs.length === 0 && (
          <div className="bg-white border border-gray-200 rounded-xl p-8 text-center">
            <p className="text-gray-500 text-sm">No jobs posted yet.</p>
          </div>
        )}
      </div>
    </main>
  );
}

function BackLink() {
  return (
    <Link
      href="/admin/employers"
      className="text-sm text-gray-500 hover:text-gray-700 inline-flex items-center gap-1"
    >
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
    <div className={`bg-white border rounded-lg p-4 ${job.is_active ? "border-gray-200" : "border-gray-100 opacity-70"}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-gray-900">{job.title}</span>
            {!job.is_active && (
              <span className="text-xs bg-gray-100 text-gray-500 border border-gray-200 rounded px-1.5 py-0.5">
                Inactive
              </span>
            )}
            {job.experience_level && (
              <span className="text-xs bg-blue-50 text-blue-700 border border-blue-100 rounded px-1.5 py-0.5 capitalize">
                {job.experience_level}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5 text-xs text-gray-500">
            {location && <span>{location}</span>}
            {setting && <span>{setting}</span>}
            {pay && <span className="text-gray-700 font-medium">{pay}</span>}
          </div>
        </div>

        {/* Applicant counts + actions */}
        <div className="shrink-0 flex items-center gap-4">
          <div className="flex gap-3 text-right">
            <div>
              <div className="text-base font-bold text-green-700 leading-none">{job.eligible_count}</div>
              <div className="text-xs text-gray-400 mt-0.5">eligible</div>
            </div>
            <div>
              <div className="text-base font-bold text-orange-600 leading-none">{job.near_fit_count}</div>
              <div className="text-xs text-gray-400 mt-0.5">near fit</div>
            </div>
          </div>

          <div className="flex items-center gap-2 border-l border-gray-100 pl-4">
            <Link
              href={`/employer/jobs/${job.id}/applicants`}
              className="inline-flex items-center gap-1 text-xs font-medium text-spf-navy hover:underline"
            >
              <Users className="w-3.5 h-3.5" /> Matched candidates ({job.total_visible})
            </Link>
            {job.source_url && (
              <a
                href={job.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600"
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
