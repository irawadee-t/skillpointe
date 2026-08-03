/**
 * Admin Employers Directory
 *
 * Org-profile directory with granular, data-backed filtering: name search,
 * state + industry multi-selects, partner status, job-count bands, hiring
 * activity (real engagement data), careers-source connection, and date added.
 * All filters are URL-synced and compose (AND across facets).
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { MessageSquare, MapPin, Building2, ArrowRight, Link2 } from "lucide-react";

import { fetchAdminEmployers } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import {
  PageHeader,
  Reveal,
  Stagger,
  StaggerItem,
  Breadcrumb,
  UrlSelectField,
  UrlMultiSelectField,
  UrlDateField,
  ActiveFilterChips,
  FilterBar,
  FilterGroup,
  FilterTransition,
  SearchSuggestField,
  describeActiveFilters,
  type FilterChipDef,
} from "@/components/ui";
import { PagerJump } from "@/components/admin/PagerJump";

interface PageProps {
  searchParams: Promise<{
    q?: string;
    states?: string;
    industry?: string;
    is_partner?: string;
    has_active_jobs?: string;
    jobs_band?: string;
    has_hired?: string;
    has_outreach?: string;
    has_career_source?: string;
    created_from?: string;
    created_to?: string;
    sort?: string;
    page?: string;
  }>;
}

const BOOL_OPTIONS = (yes: string, no: string) => [
  { value: "true", label: yes },
  { value: "false", label: no },
];

const JOBS_BAND_OPTIONS = [
  { value: "none", label: "No jobs" },
  { value: "1_10", label: "1–10 jobs" },
  { value: "11_100", label: "11–100 jobs" },
  { value: "over_100", label: "100+ jobs" },
];

function parseBool(v: string | undefined): boolean | undefined {
  return v === "true" ? true : v === "false" ? false : undefined;
}

export default async function AdminEmployersPage({ searchParams }: PageProps) {
  const sp = await searchParams;

  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  const page = sp.page ? Math.max(1, parseInt(sp.page)) : 1;

  let data;
  try {
    data = await fetchAdminEmployers(session.access_token, {
      q: sp.q,
      states: sp.states,
      industry: sp.industry,
      is_partner: parseBool(sp.is_partner),
      has_active_jobs: parseBool(sp.has_active_jobs),
      jobs_band: sp.jobs_band,
      has_hired: parseBool(sp.has_hired),
      has_outreach: parseBool(sp.has_outreach),
      has_career_source: parseBool(sp.has_career_source),
      created_from: sp.created_from,
      created_to: sp.created_to,
      sort: sp.sort,
      page,
    });
  } catch (e) {
    return (
      <main className="py-8">
        <div className="page-shell bg-error-red/[0.06] border border-error-red/30 rounded-md p-5 text-body text-cohere-ink">
          {e instanceof ApiError ? `API error ${e.status}` : "Could not reach the API. Please refresh."}
        </div>
      </main>
    );
  }

  const chipFields: FilterChipDef[] = [
    { param: "q", label: "Name" },
    { param: "states", label: "State", multi: true },
    { param: "industry", label: "Industry", multi: true },
    { param: "is_partner", label: "Partner", options: BOOL_OPTIONS("Partners only", "Non-partners") },
    { param: "has_active_jobs", label: "Active jobs", options: BOOL_OPTIONS("Has active", "None active") },
    { param: "jobs_band", label: "Job count", options: JOBS_BAND_OPTIONS },
    { param: "has_hired", label: "Hiring", options: BOOL_OPTIONS("Has hired", "No hires") },
    { param: "has_outreach", label: "Outreach", options: BOOL_OPTIONS("Has sent", "None sent") },
    { param: "has_career_source", label: "Careers source", options: BOOL_OPTIONS("Connected", "Not connected") },
    { param: "created_from", label: "Added from" },
    { param: "created_to", label: "Added to" },
  ];
  const hasFilters = chipFields.some((f) => !!sp[f.param as keyof typeof sp]);
  const filterSentence = describeActiveFilters(sp as Record<string, string | undefined>, chipFields);

  const from = data.total === 0 ? 0 : (page - 1) * 50 + 1;
  const to = Math.min(page * 50, data.total);

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

        {/* Filter bar — 4 primary controls; long tail behind "More filters" */}
        <Reveal>
          <FilterBar
            footer={<ActiveFilterChips fields={chipFields} className="mt-3" />}
            moreParams={[
              "is_partner",
              "jobs_band",
              "has_active_jobs",
              "has_hired",
              "has_outreach",
              "has_career_source",
              "created_from",
              "created_to",
            ]}
            primary={
              <>
                <SearchSuggestField
                  param="q"
                  suggest="admin-employers"
                  label="Search company name"
                  placeholder="Acme Industrial…"
                  className="flex-1 min-w-[180px]"
                  inputClassName="px-3 py-2 pl-9 text-body"
                />
                <UrlMultiSelectField
                  param="states"
                  label="State"
                  options={data.facets.states.map((s) => ({ value: s, label: s }))}
                  className="min-w-[110px]"
                />
                <UrlMultiSelectField
                  param="industry"
                  label="Industry"
                  options={data.facets.industries.map((i) => ({ value: i, label: i }))}
                  className="min-w-[150px]"
                />
                <UrlSelectField
                  param="sort"
                  label="Sort"
                  className="min-w-[130px]"
                  selectClassName="px-2 py-2 text-body"
                  options={[
                    { value: "", label: "Name" },
                    { value: "jobs", label: "Most jobs" },
                    { value: "recent", label: "Recent activity" },
                  ]}
                />
              </>
            }
          >
            <FilterGroup label="Partnership">
              <UrlSelectField
                param="is_partner"
                label="Partner status"
                className="min-w-[130px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "All" }, ...BOOL_OPTIONS("Partners only", "Non-partners")]}
              />
              <UrlSelectField
                param="has_career_source"
                label="Careers source"
                className="min-w-[130px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...BOOL_OPTIONS("Connected", "Not connected")]}
              />
            </FilterGroup>
            <FilterGroup label="Jobs & hiring activity">
              <UrlSelectField
                param="jobs_band"
                label="Job count"
                className="min-w-[120px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...JOBS_BAND_OPTIONS]}
              />
              <UrlSelectField
                param="has_active_jobs"
                label="Active jobs"
                className="min-w-[120px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...BOOL_OPTIONS("Has active", "None active")]}
              />
              <UrlSelectField
                param="has_hired"
                label="Hiring"
                className="min-w-[120px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...BOOL_OPTIONS("Has hired", "No hires")]}
              />
              <UrlSelectField
                param="has_outreach"
                label="Outreach"
                className="min-w-[120px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...BOOL_OPTIONS("Has sent", "None sent")]}
              />
            </FilterGroup>
            <FilterGroup label="Date added">
              <UrlDateField
                param="created_from"
                label="Added from"
                className="min-w-[140px]"
                inputClassName="px-2 py-1.5 text-body"
              />
              <UrlDateField
                param="created_to"
                label="Added to"
                className="min-w-[140px]"
                inputClassName="px-2 py-1.5 text-body"
              />
            </FilterGroup>
          </FilterBar>
        </Reveal>

        {/* Result count — same predicates as the list (parity-tested server-side).
            FilterTransition fades fresh results in (~150ms) on filter changes. */}
        <FilterTransition className="space-y-6">
        <p className="text-body text-slate" aria-live="polite">
          Showing {from}–{to} of {data.total}
          {hasFilters ? " matching employers" : " employers"}
        </p>

        {/* Results */}
        {data.employers.length === 0 ? (
          <div className="rounded-[10px] border border-hairline bg-white p-8 text-center">
            <p className="text-ink font-medium">
              {hasFilters ? "No employers match these filters" : "No employers found"}
            </p>
            {hasFilters && (
              <p className="text-body text-slate mt-1">
                Active filters: {filterSentence || "none"}. Remove one, or clear all to widen the results.
              </p>
            )}
          </div>
        ) : (
          <Stagger className="space-y-3">
            {data.employers.map((emp) => {
              const location = [emp.city, emp.state].filter(Boolean).join(", ");
              return (
                <StaggerItem
                  key={emp.id}
                  className="rounded-[14px] border border-hairline bg-white p-5 transition-[color,background-color,border-color,box-shadow] duration-200 ease-cohere hover:shadow-float"
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
                          // Emphasis, not a status — solid ink so maroon stays
                          // reserved for attention states.
                          <span className="inline-flex items-center rounded-full border border-cohere-ink bg-ink px-2 py-0.5 text-[11px] font-medium text-white">
                            Partner
                          </span>
                        )}
                        {emp.has_career_source && (
                          <span className="inline-flex items-center gap-1 rounded-full border border-hairline px-2 py-0.5 text-[11px] font-medium text-slate">
                            <Link2 className="h-3 w-3" /> Careers source
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
                        {(emp.hired_count > 0 || emp.outreach_count > 0) && (
                          <span className="tabular-nums">
                            {emp.hired_count > 0 && `${emp.hired_count} hired`}
                            {emp.hired_count > 0 && emp.outreach_count > 0 && " · "}
                            {emp.outreach_count > 0 && `${emp.outreach_count} outreach sent`}
                          </span>
                        )}
                        {emp.contact_name && (
                          <span className="text-slate font-medium">{emp.contact_name}</span>
                        )}
                      </div>
                    </div>

                    {/* Job counts — clickable, link into filtered jobs list */}
                    <div className="shrink-0 flex flex-col items-end gap-1 text-caption">
                      <Link
                        href={`/admin/employers/${emp.id}?jobs=active`}
                        className="group inline-flex items-center gap-1 text-slate hover:text-cohere-ink transition-colors"
                      >
                        <span className="font-medium text-cohere-ink tabular-nums">{emp.active_jobs}</span>
                        active jobs
                        <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
                      </Link>
                      <Link
                        href={`/admin/employers/${emp.id}?jobs=all`}
                        className="group inline-flex items-center gap-1 text-slate hover:text-cohere-ink transition-colors"
                      >
                        <span className="font-medium text-cohere-ink tabular-nums">{emp.total_jobs}</span>
                        total jobs
                        <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
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
              Showing {from}–{to} of {data.total}
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
        </FilterTransition>
      </div>
    </main>
  );
}
