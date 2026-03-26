/**
 * Admin Employers Directory
 *
 * Lists all employers with search and filter controls.
 * Admin can see contact emails, partner status, and job counts.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { Mail, MapPin, Building2, Star } from "lucide-react";

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
        <div className="max-w-5xl mx-auto bg-red-50 border border-red-200 rounded-xl p-5 text-sm text-red-800">
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
            <h1 className="text-2xl font-bold text-spf-navy">Employers</h1>
            <p className="text-sm text-gray-500 mt-0.5">{data.total} total</p>
          </div>
          <Link href="/admin" className="text-sm text-gray-500 hover:text-gray-700">
            ← Dashboard
          </Link>
        </div>

        {/* Filter bar */}
        <form method="GET" action="/admin/employers" className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[180px]">
              <label className="block text-xs text-gray-500 mb-1">Search company name</label>
              <input
                name="q"
                type="text"
                defaultValue={sp.q ?? ""}
                placeholder="Acme Industrial…"
                className="w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm"
              />
            </div>
            <div className="min-w-[90px]">
              <label className="block text-xs text-gray-500 mb-1">State</label>
              <input
                name="state"
                type="text"
                maxLength={2}
                defaultValue={sp.state ?? ""}
                placeholder="TX"
                className="w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm uppercase"
              />
            </div>
            <div className="min-w-[130px]">
              <label className="block text-xs text-gray-500 mb-1">Partner status</label>
              <select
                name="is_partner"
                defaultValue={sp.is_partner ?? ""}
                className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm"
              >
                <option value="">All</option>
                <option value="true">Partners only</option>
                <option value="false">Non-partners</option>
              </select>
            </div>
            <button
              type="submit"
              className="px-4 py-1.5 bg-spf-navy text-white text-sm font-medium rounded-md hover:bg-spf-navy/90"
            >
              Search
            </button>
            {hasFilters && (
              <Link
                href="/admin/employers"
                className="px-3 py-1.5 text-sm text-gray-500 border border-gray-200 rounded-md hover:bg-gray-50"
              >
                Clear
              </Link>
            )}
          </div>
        </form>

        {/* Results */}
        {data.employers.length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-xl p-8 text-center">
            <p className="text-gray-600 font-medium">No employers found</p>
            {hasFilters && (
              <p className="text-sm text-gray-500 mt-1">Try adjusting your filters.</p>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {data.employers.map((emp) => {
              const location = [emp.city, emp.state].filter(Boolean).join(", ");
              return (
                <div
                  key={emp.id}
                  className="bg-white border border-gray-200 rounded-xl p-5 hover:border-gray-300 hover:shadow-sm transition-all"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Link
                          href={`/admin/employers/${emp.id}`}
                          className="font-semibold text-gray-900 hover:text-spf-navy hover:underline"
                        >
                          {emp.name}
                        </Link>
                        {emp.is_partner && (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-spf-orange bg-orange-50 border border-orange-200 rounded-md px-2 py-0.5">
                            <Star className="w-3 h-3 fill-spf-orange" /> Partner
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-sm text-gray-500">
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
                          <span className="text-gray-600 font-medium">{emp.contact_name}</span>
                        )}
                      </div>
                    </div>

                    {/* Job counts */}
                    <div className="shrink-0 flex gap-3 text-right">
                      <div>
                        <div className="text-lg font-bold text-green-700 leading-none">{emp.active_jobs}</div>
                        <div className="text-xs text-gray-400 mt-0.5">active jobs</div>
                      </div>
                      <div>
                        <div className="text-lg font-bold text-gray-700 leading-none">{emp.total_jobs}</div>
                        <div className="text-xs text-gray-400 mt-0.5">total jobs</div>
                      </div>
                    </div>
                  </div>

                  {/* Contact row */}
                  <div className="mt-3 pt-3 border-t border-gray-100 flex items-center gap-4 flex-wrap">
                    {emp.contact_email ? (
                      <>
                        <span className="text-sm text-gray-500 font-mono">{emp.contact_email}</span>
                        <a
                          href={`mailto:${emp.contact_email}`}
                          className="inline-flex items-center gap-1 text-sm font-medium text-spf-navy hover:text-spf-navy/80"
                        >
                          <Mail className="w-3.5 h-3.5" /> Send email
                        </a>
                      </>
                    ) : (
                      <span className="text-xs text-gray-400 italic">No contact on file</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Pagination */}
        {data.total > 50 && (
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              Showing {(page - 1) * 50 + 1}–{Math.min(page * 50, data.total)} of {data.total}
            </span>
            <div className="flex gap-2">
              {page > 1 && (
                <Link
                  href={`/admin/employers?${new URLSearchParams({ ...sp, page: String(page - 1) })}`}
                  className="px-3 py-1 border border-gray-200 rounded-md hover:bg-gray-50"
                >
                  Previous
                </Link>
              )}
              {page * 50 < data.total && (
                <Link
                  href={`/admin/employers?${new URLSearchParams({ ...sp, page: String(page + 1) })}`}
                  className="px-3 py-1 border border-gray-200 rounded-md hover:bg-gray-50"
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
