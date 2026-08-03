/**
 * Public employer profile — visible to any signed-in user.
 * Not to be confused with /admin/employers/[id] which is the admin's inspection view.
 */
import { redirect } from "next/navigation";
import Link from "next/link";

import { createClient } from "@/lib/supabase/server";
import { getEmployerPublic } from "@/lib/api/transactions";
import { PageHeader, MonoLabel } from "@/components/ui";
import { Building2, MapPin, Globe, ShieldCheck, ArrowLeft, Briefcase } from "lucide-react";

export default async function EmployerPublicPage({
  params,
}: { params: Promise<{ employerId: string }> }) {
  const { employerId } = await params;
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");

  let emp = null;
  try { emp = await getEmployerPublic(session.access_token, employerId); }
  catch { /* ignore */ }

  if (!emp) {
    return (
      <main className="py-8">
        <div className="page-shell">
          <div className="rounded-xl border border-cohere-coral/30 bg-cohere-coral/[0.06] p-6 text-body">
            We couldn't load this employer. They may have been removed.
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Link href="javascript:history.back()" className="inline-flex items-center gap-1 text-caption text-slate hover:text-cohere-ink">
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </Link>

        <PageHeader
          eyebrow="Employer"
          title={emp.name}
          lead={emp.description ?? undefined}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              {emp.verified_worker_count > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-cohere-green bg-cohere-green px-2.5 py-0.5 text-micro font-medium text-white" title="Applicants with verified credentials who were hired here.">
                  <ShieldCheck className="h-3 w-3" />
                  {emp.verified_worker_count} verified worker{emp.verified_worker_count === 1 ? "" : "s"} here
                </span>
              )}
              {emp.open_job_count > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-cohere-blue bg-cohere-blue px-2.5 py-0.5 text-micro font-medium text-white">
                  <Briefcase className="h-3 w-3" />
                  {emp.open_job_count} open job{emp.open_job_count === 1 ? "" : "s"}
                </span>
              )}
            </div>
          }
        />

        {/* Employer facts */}
        <section className="grid gap-4 rounded-xl border border-hairline bg-white p-6 sm:grid-cols-3">
          <Fact icon={Building2} label="Industry" value={emp.industry} />
          <Fact icon={MapPin} label="Location" value={[emp.city, emp.state].filter(Boolean).join(", ") || null} />
          {emp.website && (
            <div>
              <MonoLabel className="mb-0.5 block">Website</MonoLabel>
              <a href={emp.website} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-body text-cohere-blue hover:underline">
                <Globe className="h-3.5 w-3.5" /> {new URL(emp.website).hostname}
              </a>
            </div>
          )}
        </section>

        {/* Jobs */}
        {emp.jobs.length > 0 && (
          <section>
            <MonoLabel className="mb-3 block">Open positions</MonoLabel>
            <div className="grid gap-3 sm:grid-cols-2">
              {emp.jobs.map((j) => (
                <Link
                  key={j.id}
                  href={`/applicant/jobs?q=${encodeURIComponent(j.title)}`}
                  className="group rounded-xl border border-hairline bg-white p-4 transition-shadow hover:shadow-[0_6px_20px_-10px_rgba(12,10,9,0.14)]"
                >
                  <div className="font-medium text-cohere-ink">{j.title}</div>
                  <div className="mt-1 text-caption text-slate">
                    {[j.city, j.state].filter(Boolean).join(", ") || "Location TBD"}
                    {j.work_setting && <span className="ml-2 text-slate-muted">{j.work_setting}</span>}
                  </div>
                </Link>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}

function Fact({ icon: Icon, label, value }: { icon: typeof MapPin; label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div>
      <MonoLabel className="mb-0.5 block">{label}</MonoLabel>
      <p className="inline-flex items-center gap-1.5 text-body text-cohere-ink">
        <Icon className="h-3.5 w-3.5 text-slate-muted" strokeWidth={1.75} />
        {value}
      </p>
    </div>
  );
}
