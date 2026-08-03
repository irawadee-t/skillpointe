/**
 * Admin Applicants Directory
 *
 * Lists all applicants with search and filter controls.
 * Admin can see contact emails and match stats, and open a mailto: link.
 */
import Link from "next/link";
import { redirect } from "next/navigation";

import { fetchAdminApplicants } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { PageHeader, Reveal, Breadcrumb, UrlSearchField, SearchSuggestField, FilterTransition } from "@/components/ui";
import { PagerJump } from "@/components/admin/PagerJump";
import { ApplicantsGridClient } from "./ApplicantsGridClient";

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
        <div className="max-w-5xl mx-auto bg-error-red/[0.06] border border-error-red/30 rounded-md p-5 text-caption text-cohere-ink">
          {e instanceof ApiError ? `API error ${e.status}` : "Could not reach the API. Please refresh."}
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

        {/* Filter bar — live type-ahead: results narrow with every letter */}
        <Reveal>
          <div className="border border-border-light rounded-md bg-white p-4" data-tour-id="applicants-filters">
            <div className="flex flex-wrap gap-3 items-end">
              <SearchSuggestField
                param="q"
                suggest="admin-applicants"
                label="Search name / email"
                placeholder="Jane Doe or jane@…"
                className="flex-1 min-w-[180px]"
                inputClassName="px-3 py-1.5 pl-9 text-caption"
              />
              <UrlSearchField
                param="state"
                label="State"
                placeholder="TX"
                maxLength={2}
                uppercase
                className="min-w-[90px]"
                inputClassName="px-3 py-1.5 pl-9 text-caption"
              />
              <UrlSearchField
                param="job_family"
                label="Job family"
                placeholder="welding, hvac…"
                className="min-w-[160px]"
                inputClassName="px-3 py-1.5 pl-9 text-caption"
              />
              {hasFilters && (
                <Link href="/admin/applicants" className="btn-pill-outline">
                  Clear
                </Link>
              )}
            </div>
          </div>
        </Reveal>

        {/* Results — the operator DataGrid (sortable, keyboard-navigable).
            Empty state is built in; filters + pagination stay server-side.
            FilterTransition fades the fresh rows in (~150ms) on each filter
            or search change instead of an abrupt swap. */}
        <FilterTransition className="space-y-6">
        <div data-tour-id="applicants-table">
        <ApplicantsGridClient
          rows={data.applicants}
          emptyMessage={
            sp.q
              ? `No results for “${sp.q}”.${hasFilters ? " Try adjusting your filters." : ""}`
              : hasFilters
                ? "No applicants found. Try adjusting your filters."
                : "No applicants found."
          }
        />
        </div>


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
        </FilterTransition>
      </div>
    </main>
  );
}

