/**
 * Admin Employers Directory
 *
 * Lists all employers with search and filter controls.
 * Admin can see contact emails, partner status, and job counts.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { Mail, MapPin, Building2 } from "lucide-react";

import { fetchAdminEmployers } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";

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
      <main className="p-6 md:p-8">
        <div className="max-w-5xl mx-auto bg-rose-50 border border-rose-200 rounded-lg p-5 text-sm text-rose-600">
          {e instanceof ApiError ? `API error ${e.status}` : "Could not reach the API — please refresh."}
        </div>
      </main>
    );
  }

  const hasFilters = !!(sp.q || sp.state || sp.is_partner);

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Employers</h1>
            <p className="text-sm text-zinc-500 mt-0.5">{data.total} total</p>
          </div>
          <Link href="/admin" className="text-sm text-zinc-500 hover:text-zinc-900 transition-colors">
            ← Dashboard
          </Link>
        </div>

        {/* Filter bar */}
        <form method="GET" action="/admin/employers" className="bg-zinc-50 border border-zinc-200 rounded-lg p-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[180px]">
              <label className="block text-xs text-zinc-400 mb-1">Search company name</label>
              <input
                name="q"
                type="text"
                defaultValue={sp.q ?? ""}
                placeholder="Acme Industrial…"
                className="w-full border border-zinc-200 rounded-md px-3 py-1.5 text-sm bg-white text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-spf-navy/20 focus:border-spf-navy"
              />
            </div>
            <div className="min-w-[90px]">
              <label className="block text-xs text-zinc-400 mb-1">State</label>
              <input
                name="state"
                type="text"
                maxLength={2}
                defaultValue={sp.state ?? ""}
                placeholder="TX"
                className="w-full border border-zinc-200 rounded-md px-3 py-1.5 text-sm bg-white text-zinc-900 placeholder:text-zinc-400 uppercase focus:outline-none focus:ring-1 focus:ring-spf-navy/20 focus:border-spf-navy"
              />
            </div>
            <div className="min-w-[130px]">
              <label className="block text-xs text-zinc-400 mb-1">Partner status</label>
              <select
                name="is_partner"
                defaultValue={sp.is_partner ?? ""}
                className="w-full border border-zinc-200 rounded-md px-2 py-1.5 text-sm bg-white text-zinc-900 focus:outline-none focus:ring-1 focus:ring-spf-navy/20 focus:border-spf-navy"
              >
                <option value="">All</option>
                <option value="true">Partners only</option>
                <option value="false">Non-partners</option>
              </select>
            </div>
            <button
              type="submit"
              className="px-4 py-1.5 bg-zinc-900 text-white text-sm font-medium rounded-full hover:bg-zinc-700 transition-colors"
            >
              Search
            </button>
            {hasFilters && (
              <Link
                href="/admin/employers"
                className="px-3 py-1.5 text-sm text-zinc-500 border border-zinc-200 rounded-full hover:border-zinc-300 hover:text-zinc-700 transition-colors"
              >
                Clear
              </Link>
            )}
          </div>
        </form>

        {/* Results */}
        {data.employers.length === 0 ? (
          <div className="bg-zinc-50 border border-zinc-200 rounded-lg p-8 text-center">
            <p className="text-zinc-600 font-medium">No employers found</p>
            {hasFilters && (
              <p className="text-sm text-zinc-400 mt-1">Try adjusting your filters.</p>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {data.employers.map((emp) => {
              const location = [emp.city, emp.state].filter(Boolean).join(", ");
              return (
                <div
                  key={emp.id}
                  className="bg-zinc-50 border border-zinc-200 rounded-lg p-5 hover:border-zinc-300 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Link
                          href={`/admin/employers/${emp.id}`}
                          className="font-semibold text-zinc-900 hover:text-spf-navy transition-colors"
                        >
                          {emp.name}
                        </Link>
                        {emp.is_partner && (
                          <span className="inline-flex items-center text-xs font-medium text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-full px-2 py-0.5">
                            Partner
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-sm text-zinc-500">
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
                          <span className="text-zinc-600 font-medium">{emp.contact_name}</span>
                        )}
                      </div>
                    </div>

                    {/* Job counts */}
                    <div className="shrink-0 flex gap-3 text-right">
                      <div>
                        <div className="text-lg font-bold text-spf-navy leading-none">{emp.active_jobs}</div>
                        <div className="text-xs text-zinc-400 mt-0.5">active jobs</div>
                      </div>
                      <div>
                        <div className="text-lg font-bold text-zinc-500 leading-none">{emp.total_jobs}</div>
                        <div className="text-xs text-zinc-400 mt-0.5">total jobs</div>
                      </div>
                    </div>
                  </div>

                  {/* Contact row */}
                  <div className="mt-3 pt-3 border-t border-zinc-200 flex items-center gap-4 flex-wrap">
                    {emp.contact_email ? (
                      <>
                        <span className="text-sm text-zinc-400 font-mono">{emp.contact_email}</span>
                        <a
                          href={`mailto:${emp.contact_email}`}
                          className="inline-flex items-center gap-1 text-sm font-medium text-spf-navy hover:text-spf-navy-light transition-colors"
                        >
                          <Mail className="w-3.5 h-3.5" /> Send email
                        </a>
                      </>
                    ) : (
                      <span className="text-xs text-zinc-400 italic">No contact on file</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Pagination */}
        {data.total > 50 && (
          <div className="flex items-center justify-between text-sm text-zinc-400">
            <span>
              Showing {(page - 1) * 50 + 1}–{Math.min(page * 50, data.total)} of {data.total}
            </span>
            <div className="flex gap-2">
              {page > 1 && (
                <Link
                  href={`/admin/employers?${new URLSearchParams({ ...sp, page: String(page - 1) })}`}
                  className="px-3 py-1 border border-zinc-200 rounded-full hover:border-zinc-300 hover:text-zinc-600 transition-colors"
                >
                  Previous
                </Link>
              )}
              {page * 50 < data.total && (
                <Link
                  href={`/admin/employers?${new URLSearchParams({ ...sp, page: String(page + 1) })}`}
                  className="px-3 py-1 border border-zinc-200 rounded-full hover:border-zinc-300 hover:text-zinc-600 transition-colors"
                >
                  Next
                </Link>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
