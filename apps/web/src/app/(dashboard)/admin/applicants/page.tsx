/**
 * Admin Applicants Directory
 *
 * Lists all applicants with search and filter controls.
 * Admin can see contact emails and match stats, and open a mailto: link.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { Mail, MapPin, Briefcase, Calendar, ArrowUpRight } from "lucide-react";

import { fetchAdminApplicants } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";

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
        <div className="max-w-5xl mx-auto bg-rose-500/10 border border-rose-500/30 rounded-lg p-5 text-sm text-rose-400">
          {e instanceof ApiError ? `API error ${e.status}` : "Could not reach the API — please refresh."}
        </div>
      </main>
    );
  }

  const hasFilters = !!(sp.q || sp.state || sp.job_family);

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-white">Applicants</h1>
            <p className="text-sm text-zinc-400 mt-0.5">{data.total} total</p>
          </div>
          <Link href="/admin" className="text-sm text-zinc-400 hover:text-white transition-colors">
            ← Dashboard
          </Link>
        </div>

        {/* Filter bar */}
        <form method="GET" action="/admin/applicants" className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[180px]">
              <label className="block text-xs text-zinc-500 mb-1">Search name / email</label>
              <input
                name="q"
                type="text"
                defaultValue={sp.q ?? ""}
                placeholder="Jane Doe or jane@…"
                className="w-full border border-zinc-700 rounded-md px-3 py-1.5 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
              />
            </div>
            <div className="min-w-[90px]">
              <label className="block text-xs text-zinc-500 mb-1">State</label>
              <input
                name="state"
                type="text"
                maxLength={2}
                defaultValue={sp.state ?? ""}
                placeholder="TX"
                className="w-full border border-zinc-700 rounded-md px-3 py-1.5 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 uppercase focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
              />
            </div>
            <div className="min-w-[160px]">
              <label className="block text-xs text-zinc-500 mb-1">Job family</label>
              <input
                name="job_family"
                type="text"
                defaultValue={sp.job_family ?? ""}
                placeholder="welding, hvac…"
                className="w-full border border-zinc-700 rounded-md px-3 py-1.5 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
              />
            </div>
            <button
              type="submit"
              className="px-4 py-1.5 bg-cyan-500 text-black text-sm font-medium rounded-full hover:bg-cyan-400 transition-colors"
            >
              Search
            </button>
            {hasFilters && (
              <Link
                href="/admin/applicants"
                className="px-3 py-1.5 text-sm text-zinc-400 border border-zinc-700 rounded-full hover:border-zinc-500 hover:text-zinc-200 transition-colors"
              >
                Clear
              </Link>
            )}
          </div>
        </form>

        {/* Results */}
        {data.applicants.length === 0 ? (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center">
            <p className="text-zinc-300 font-medium">No applicants found</p>
            {hasFilters && (
              <p className="text-sm text-zinc-500 mt-1">Try adjusting your filters.</p>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {data.applicants.map((a) => {
              const fullName = [a.first_name, a.last_name].filter(Boolean).join(" ") || "Unnamed";
              const location = [a.city, a.state].filter(Boolean).join(", ");
              return (
                <div
                  key={a.id}
                  className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 hover:border-zinc-700 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-semibold text-white">{fullName}</h3>
                        {a.profile_completeness >= 80 && (
                          <span className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded-full px-2 py-0.5">
                            {a.profile_completeness}% complete
                          </span>
                        )}
                        {a.profile_completeness < 80 && a.profile_completeness > 0 && (
                          <span className="text-xs text-zinc-400 bg-zinc-800 border border-zinc-700 rounded-full px-2 py-0.5">
                            {a.profile_completeness}% complete
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-sm text-zinc-400">
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
                          <span className="flex items-center gap-1 text-zinc-400">
                            <ArrowUpRight className="w-3.5 h-3.5" /> Open to relocate
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Match stats */}
                    <div className="shrink-0 flex gap-3 text-right">
                      <div>
                        <div className="text-lg font-bold text-emerald-400 leading-none">{a.eligible_count}</div>
                        <div className="text-xs text-zinc-500 mt-0.5">eligible</div>
                      </div>
                      <div>
                        <div className="text-lg font-bold text-amber-400 leading-none">{a.near_fit_count}</div>
                        <div className="text-xs text-zinc-500 mt-0.5">near fit</div>
                      </div>
                    </div>
                  </div>

                  {/* Contact row */}
                  {a.email && (
                    <div className="mt-3 pt-3 border-t border-zinc-800 flex items-center gap-4">
                      <span className="text-sm text-zinc-500 font-mono">{a.email}</span>
                      <a
                        href={`mailto:${a.email}`}
                        className="inline-flex items-center gap-1 text-sm font-medium text-cyan-400 hover:text-cyan-300 transition-colors"
                      >
                        <Mail className="w-3.5 h-3.5" /> Send email
                      </a>
                    </div>
                  )}
                  {!a.email && (
                    <div className="mt-3 pt-3 border-t border-zinc-800">
                      <span className="text-xs text-zinc-600 italic">No email on file</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Pagination */}
        {data.total > 50 && (
          <div className="flex items-center justify-between text-sm text-zinc-500">
            <span>
              Showing {(page - 1) * 50 + 1}–{Math.min(page * 50, data.total)} of {data.total}
            </span>
            <div className="flex gap-2">
              {page > 1 && (
                <Link
                  href={`/admin/applicants?${new URLSearchParams({ ...sp, page: String(page - 1) })}`}
                  className="px-3 py-1 border border-zinc-700 rounded-full hover:border-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  Previous
                </Link>
              )}
              {page * 50 < data.total && (
                <Link
                  href={`/admin/applicants?${new URLSearchParams({ ...sp, page: String(page + 1) })}`}
                  className="px-3 py-1 border border-zinc-700 rounded-full hover:border-zinc-500 hover:text-zinc-300 transition-colors"
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
