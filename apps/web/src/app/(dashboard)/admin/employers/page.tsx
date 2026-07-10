/**
 * Admin Employers Directory
 *
 * Lists all employers with search and filter controls.
 * Admin can see contact emails, partner status, and job counts.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { MessageSquare, MapPin, Building2, ArrowRight } from "lucide-react";

import { fetchAdminEmployers } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { PageHeader, Reveal, Stagger, StaggerItem, MetricCard, Breadcrumb } from "@/components/ui";
import { PagerJump } from "@/components/admin/PagerJump";

interface PageProps {
  searchParams: Promise<{
    q?: string;
    state?: string;
    is_partner?: string;
    page?: string;
  }>;
}

export default async function AdminEmployersPage({ searchParams }: PageProps) {
  const sp = await searchParams;

  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  const page = sp.page ? Math.max(1, parseInt(sp.page)) : 1;
  const isPartnerFilter =
    sp.is_partner === "true" ? true : sp.is_partner === "false" ? false : undefined;

  let data;
  try {
    data = await fetchAdminEmployers(session.access_token, {
      q: sp.q,
      state: sp.state,
      is_partner: isPartnerFilter,
      page,
    });
  } catch (e) {
    return (
      <main className="py-8">
        <div className="page-shell bg-cohere-coral/10 border border-cohere-coral-soft rounded-md p-5 text-body text-cohere-ink">
          {e instanceof ApiError ? `API error ${e.status}` : "Could not reach the API — please refresh."}
        </div>
      </main>
    );
  }

  const hasFilters = !!(sp.q || sp.state || sp.is_partner);
  const partnerCount = data.employers.filter((emp) => emp.is_partner).length;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Employers" }]} />
        {/* Header */}
        <PageHeader
          eyebrow="Directory"
          title="Employers"
          lead={`${data.total} total`}
          actions={
            <Link href="/admin" className="btn-secondary">
              ← Dashboard
            </Link>
          }
        />

        {/* Stat cards — deep-green KPIs */}
        <Stagger className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <StaggerItem>
            <MetricCard label="Total employers" value={data.total.toLocaleString()} icon={Building2} />
          </StaggerItem>
          <StaggerItem>
            <MetricCard label="Partners (this page)" value={partnerCount.toLocaleString()} icon={MessageSquare} />
          </StaggerItem>
          <StaggerItem>
            <MetricCard
              label="Active jobs (this page)"
              value={data.employers.reduce((n, e) => n + e.active_jobs, 0).toLocaleString()}
              icon={MapPin}
            />
          </StaggerItem>
        </Stagger>

        {/* Filter bar */}
        <Reveal>
          <form method="GET" action="/admin/employers" className="border border-border-light rounded-md bg-white p-4">
            <div className="flex flex-wrap gap-3 items-end">
              <div className="flex-1 min-w-[180px]">
                <label className="mono-label mb-1.5 block">Search company name</label>
                <input
                  name="q"
                  type="text"
                  defaultValue={sp.q ?? ""}
                  placeholder="Acme Industrial…"
                  className="input-cohere px-3 py-2 text-body"
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
                  className="input-cohere px-3 py-2 text-body"
                />
              </div>
              <div className="min-w-[130px]">
                <label className="mono-label mb-1.5 block">Partner status</label>
                <select
                  name="is_partner"
                  defaultValue={sp.is_partner ?? ""}
                  className="input-cohere px-2 py-2 text-body"
                >
                  <option value="">All</option>
                  <option value="true">Partners only</option>
                  <option value="false">Non-partners</option>
                </select>
              </div>
              <button type="submit" className="btn-primary px-5 py-2 text-button">
                Search
              </button>
              {hasFilters && (
                <Link href="/admin/employers" className="btn-pill-outline">
                  Clear
                </Link>
              )}
            </div>
          </form>
        </Reveal>

        {/* Results */}
        {data.employers.length === 0 ? (
          <div className="border border-border-light rounded-md bg-white p-8 text-center">
            <p className="text-ink font-medium">No employers found</p>
            {hasFilters && (
              <p className="text-body text-slate mt-1">Try adjusting your filters.</p>
            )}
          </div>
        ) : (
          <Stagger className="space-y-3">
            {data.employers.map((emp) => {
              const location = [emp.city, emp.state].filter(Boolean).join(", ");
              return (
                <StaggerItem
                  key={emp.id}
                  className="rounded-md border border-hairline bg-white p-5 shadow-subtle transition-shadow hover:shadow-medium"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Link
                          href={`/admin/employers/${emp.id}`}
                          className="font-semibold text-body-lg text-cohere-ink hover:text-cohere-blue transition-colors"
                        >
                          {emp.name}
                        </Link>
                        {emp.is_partner && (
                          <span className="inline-flex items-center text-micro font-medium text-cohere-coral bg-cohere-coral/10 border border-cohere-coral-soft rounded-sm px-2 py-0.5">
                            Partner
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-body text-slate">
                        {location && (
                          <span className="flex items-center gap-1">
                            <MapPin className="w-3.5 h-3.5" /> {location}
                          </span>
                        )}
                        {emp.industry && (
                          <span className="flex items-center gap-1">
                            <Building2 className="w-3.5 h-3.5" /> {emp.industry}
                          </span>
                        )}
                        {emp.contact_name && (
                          <span className="text-slate font-medium">{emp.contact_name}</span>
                        )}
                      </div>
                    </div>

                    {/* Job counts — clickable, link into filtered jobs list */}
                    <div className="shrink-0 flex gap-3 text-center">
                      <Link
                        href={`/admin/employers/${emp.id}?jobs=active`}
                        className="group rounded-md border border-transparent bg-cohere-green px-3 py-2 transition-all hover:-translate-y-0.5 hover:border-studio-dark-cork hover:shadow-[0_6px_20px_-6px_rgba(74,75,47,0.55)]"
                      >
                        <div className="text-body-lg font-display text-studio-cream leading-none tabular-nums">{emp.active_jobs}</div>
                        <div className="mono-label mt-1 inline-flex items-center gap-1 text-studio-cream/70 group-hover:text-studio-cream transition-colors">
                          active jobs
                          <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
                        </div>
                      </Link>
                      <Link
                        href={`/admin/employers/${emp.id}?jobs=all`}
                        className="group rounded-md border border-hairline bg-white px-3 py-2 transition-all hover:-translate-y-0.5 hover:border-studio-dark-cork hover:shadow-[0_6px_20px_-6px_rgba(12,10,9,0.15)]"
                      >
                        <div className="text-body-lg font-display text-cohere-ink leading-none tabular-nums">{emp.total_jobs}</div>
                        <div className="mono-label mt-1 inline-flex items-center gap-1 group-hover:text-studio-dark-cork transition-colors">
                          total jobs
                          <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
                        </div>
                      </Link>
                    </div>
                  </div>

                  {/* Contact row */}
                  <div className="mt-3 pt-3 border-t border-hairline flex items-center gap-4 flex-wrap">
                    {emp.contact_email ? (
                      <>
                        <span className="text-body text-slate">{emp.contact_email}</span>
                        <Link
                          href={`/admin/messages/compose?employer_id=${emp.id}`}
                          className="inline-flex items-center gap-1 text-body font-medium text-studio-maroon hover:underline transition-colors"
                        >
                          <MessageSquare className="w-3.5 h-3.5" /> Send message
                        </Link>
                      </>
                    ) : (
                      <span className="text-caption text-slate italic">No contact on file</span>
                    )}
                  </div>
                </StaggerItem>
              );
            })}
          </Stagger>
        )}

        {/* Pagination */}
        {data.total > 50 && (
          <div className="flex flex-wrap items-center justify-between gap-3 text-caption text-slate">
            <span>
              Showing {(page - 1) * 50 + 1}–{Math.min(page * 50, data.total)} of {data.total}
            </span>
            <div className="flex items-center gap-3">
              <PagerJump
                basePath="/admin/employers"
                params={sp as Record<string, string | undefined>}
                page={page}
                totalPages={Math.max(1, Math.ceil(data.total / 50))}
              />
              <div className="flex gap-2">
                {page > 1 && (
                  <Link
                    href={`/admin/employers?${new URLSearchParams({ ...sp, page: String(page - 1) })}`}
                    className="btn-pill-outline"
                  >
                    Previous
                  </Link>
                )}
                {page * 50 < data.total && (
                  <Link
                    href={`/admin/employers?${new URLSearchParams({ ...sp, page: String(page + 1) })}`}
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
