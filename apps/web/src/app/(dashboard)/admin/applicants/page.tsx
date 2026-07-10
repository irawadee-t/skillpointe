/**
 * Admin Applicants Directory
 *
 * Lists all applicants with search and filter controls.
 * Admin can see contact emails and match stats, and open a mailto: link.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { MessageSquare, MapPin, Briefcase, Calendar, ArrowUpRight } from "lucide-react";

import { fetchAdminApplicants } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { PageHeader, Reveal, Stagger, StaggerItem, Breadcrumb } from "@/components/ui";
import { PagerJump } from "@/components/admin/PagerJump";
import { cn } from "@/lib/utils";

interface PageProps {
  searchParams: Promise<{
    q?: string;
    state?: string;
    job_family?: string;
    page?: string;
  }>;
}

export default async function AdminApplicantsPage({ searchParams }: PageProps) {
  const sp = await searchParams;

  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  const page = sp.page ? Math.max(1, parseInt(sp.page)) : 1;

  let data;
  try {
    data = await fetchAdminApplicants(session.access_token, {
      q: sp.q,
      state: sp.state,
      job_family: sp.job_family,
      page,
    });
  } catch (e) {
    return (
      <main className="p-6 md:p-8">
        <div className="max-w-5xl mx-auto bg-cohere-coral/10 border border-cohere-coral-soft rounded-md p-5 text-caption text-cohere-ink">
          {e instanceof ApiError ? `API error ${e.status}` : "Could not reach the API — please refresh."}
        </div>
      </main>
    );
  }

  const hasFilters = !!(sp.q || sp.state || sp.job_family);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Applicants" }]} />
        {/* Header */}
        <PageHeader
          eyebrow="Directory"
          title="Applicants"
          lead={`${data.total} total`}
          actions={
            <Link href="/admin" className="btn-secondary">
              ← Dashboard
            </Link>
          }
        />

        {/* Filter bar */}
        <Reveal>
          <form method="GET" action="/admin/applicants" className="border border-border-light rounded-md bg-white p-4">
            <div className="flex flex-wrap gap-3 items-end">
              <div className="flex-1 min-w-[180px]">
                <label className="mono-label mb-1.5 block">Search name / email</label>
                <input
                  name="q"
                  type="text"
                  defaultValue={sp.q ?? ""}
                  placeholder="Jane Doe or jane@…"
                  className="input-cohere px-3 py-1.5 text-caption"
                />
              </div>
              <div className="min-w-[90px]">
                <label className="mono-label mb-1.5 block">State</label>
                <input
                  name="state"
                  type="text"
                  maxLength={2}
                  defaultValue={sp.state ?? ""}
                  placeholder="TX"
                  className="input-cohere px-3 py-1.5 text-caption"
                />
              </div>
              <div className="min-w-[160px]">
                <label className="mono-label mb-1.5 block">Job family</label>
                <input
                  name="job_family"
                  type="text"
                  defaultValue={sp.job_family ?? ""}
                  placeholder="welding, hvac…"
                  className="input-cohere px-3 py-1.5 text-caption"
                />
              </div>
              <button type="submit" className="btn-primary px-5 py-2 text-button">
                Search
              </button>
              {hasFilters && (
                <Link href="/admin/applicants" className="btn-pill-outline">
                  Clear
                </Link>
              )}
            </div>
          </form>
        </Reveal>

        {/* Results */}
        {data.applicants.length === 0 ? (
          <div className="border border-border-light rounded-md bg-white p-8 text-center">
            <p className="text-ink font-medium">No applicants found</p>
            {hasFilters && (
              <p className="text-caption text-slate-muted mt-1">Try adjusting your filters.</p>
            )}
          </div>
        ) : (
          <Stagger className="space-y-3">
            {data.applicants.map((a) => {
              const fullName = [a.first_name, a.last_name].filter(Boolean).join(" ") || "Unnamed";
              const location = [a.city, a.state].filter(Boolean).join(", ");
              return (
                <StaggerItem
                  key={a.id}
                  className="group relative rounded-md border border-hairline bg-white px-5 py-4 shadow-subtle transition-shadow hover:shadow-medium"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <h3 className="text-body-lg font-medium text-cohere-ink">{fullName}</h3>
                        {a.profile_completeness > 0 && (
                          <span
                            className="inline-flex items-center gap-1.5 text-micro text-slate"
                            title="Based on profile fields, credentials, résumé, and program info."
                          >
                            <span className="relative inline-block h-1 w-16 overflow-hidden rounded-full bg-hairline">
                              <span
                                className={cn(
                                  "absolute inset-y-0 left-0 rounded-full",
                                  a.profile_completeness >= 80 ? "bg-cohere-green" : "bg-slate-muted",
                                )}
                                style={{ width: `${Math.min(100, a.profile_completeness)}%` }}
                              />
                            </span>
                            <span className="tabular-nums font-medium">{a.profile_completeness}%</span>
                            <span className="text-slate-muted">complete</span>
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-caption text-slate">
                        {location && (
                          <span className="flex items-center gap-1">
                            <MapPin className="w-3.5 h-3.5" /> {location}
                          </span>
                        )}
                        {a.program_name_raw && (
                          <span className="flex items-center gap-1">
                            <Briefcase className="w-3.5 h-3.5" />
                            {a.program_name_raw}
                            {a.job_family_code && ` (${a.job_family_code})`}
                          </span>
                        )}
                        {a.available_from && (
                          <span className="flex items-center gap-1">
                            <Calendar className="w-3.5 h-3.5" /> Available {a.available_from}
                          </span>
                        )}
                        {a.willing_to_relocate && (
                          <span className="flex items-center gap-1 text-slate">
                            <ArrowUpRight className="w-3.5 h-3.5" /> Open to relocate
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Match stats — compact inline, no mono labels */}
                    <div className="shrink-0 flex items-baseline gap-3 text-caption text-slate whitespace-nowrap">
                      <span>
                        <span className="tabular-nums font-medium text-cohere-ink">{a.eligible_count}</span>
                        <span className="ml-1 text-slate-muted">eligible</span>
                      </span>
                      <span aria-hidden className="text-slate-muted">—</span>
                      <span>
                        <span className="tabular-nums font-medium text-cohere-ink">{a.near_fit_count}</span>
                        <span className="ml-1 text-slate-muted">near fit</span>
                      </span>
                    </div>
                  </div>

                  {/* Contact row */}
                  {a.email && (
                    <div className="mt-3 flex items-center gap-4">
                      <span className="text-caption text-slate">{a.email}</span>
                      <Link
                        href={`/admin/messages/compose?applicant_id=${a.id}`}
                        className="inline-flex items-center gap-1 text-caption font-medium text-studio-maroon hover:underline transition-colors"
                      >
                        <MessageSquare className="w-3.5 h-3.5" /> Send message
                      </Link>
                    </div>
                  )}
                </StaggerItem>
              );
            })}
          </Stagger>
        )}

        {/* Pagination */}
        {data.total > 50 && (
          <div className="flex flex-wrap items-center justify-between gap-3 text-caption text-slate-muted">
            <span>
              Showing {(page - 1) * 50 + 1}–{Math.min(page * 50, data.total)} of {data.total}
            </span>
            <div className="flex items-center gap-3">
              <PagerJump
                basePath="/admin/applicants"
                params={sp as Record<string, string | undefined>}
                page={page}
                totalPages={Math.max(1, Math.ceil(data.total / 50))}
              />
              <div className="flex gap-2">
                {page > 1 && (
                  <Link
                    href={`/admin/applicants?${new URLSearchParams({ ...sp, page: String(page - 1) })}`}
                    className="btn-pill-outline"
                  >
                    Previous
                  </Link>
                )}
                {page * 50 < data.total && (
                  <Link
                    href={`/admin/applicants?${new URLSearchParams({ ...sp, page: String(page + 1) })}`}
                    className="btn-pill-outline"
                  >
                    Next
                  </Link>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

