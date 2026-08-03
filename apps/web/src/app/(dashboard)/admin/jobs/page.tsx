/**
 * Admin Jobs Console — /admin/jobs
 *
 * Filterable list over the ENTIRE structured job catalog (scraped + imported
 * + manual). Granular facets: family (searchable multi-select over 44
 * families), industry, state, city, employment type, pay, source + site,
 * active/inactive/stale, apply-link health, internal-apply (feature-detected),
 * posted/imported dates, and candidate bands. URL-synced; filters compose.
 */
import Link from "next/link";
import { redirect } from "next/navigation";

import { fetchAdminJobs } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import {
  PageHeader,
  Reveal,
  Breadcrumb,
  UrlSearchField,
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
import { humanizeJobSource } from "@/lib/humanize";
import { cn } from "@/lib/utils";

interface PageProps {
  searchParams: Promise<{
    q?: string;
    families?: string;
    industries?: string;
    states?: string;
    city?: string;
    employment_types?: string;
    sources?: string;
    source_sites?: string;
    status?: string;
    apply_link?: string;
    has_pay?: string;
    pay_gte?: string;
    internal_apply?: string;
    posted_from?: string;
    posted_to?: string;
    created_from?: string;
    created_to?: string;
    candidates?: string;
    sort?: string;
    page?: string;
  }>;
}

const PAGE_SIZE = 50;

const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "stale", label: "Stale (60+ days unverified)" },
];
const APPLY_LINK_OPTIONS = [
  { value: "ok", label: "Link ok" },
  { value: "broken", label: "Link broken" },
  { value: "unchecked", label: "Unchecked" },
];
const CANDIDATE_OPTIONS = [
  { value: "none", label: "No candidates" },
  { value: "1_9", label: "1–9 candidates" },
  { value: "10_49", label: "10–49 candidates" },
  { value: "over_50", label: "50+ candidates" },
];
const PAY_OPTIONS = [
  { value: "true", label: "Pay stated" },
  { value: "false", label: "No pay info" },
];

function parseBool(v: string | undefined): boolean | undefined {
  return v === "true" ? true : v === "false" ? false : undefined;
}

function formatPay(j: { pay_min: number | null; pay_max: number | null; pay_type: string | null; pay_raw: string | null }): string {
  if (j.pay_min != null) {
    const suffix = j.pay_type === "hourly" ? "/hr" : j.pay_type === "annual" ? "/yr" : "";
    const fmt = (n: number) =>
      j.pay_type === "annual" ? `$${Math.round(n / 1000)}k` : `$${n % 1 === 0 ? n.toFixed(0) : n.toFixed(2)}`;
    return j.pay_max != null && j.pay_max !== j.pay_min
      ? `${fmt(j.pay_min)}–${fmt(j.pay_max)}${suffix}`
      : `${fmt(j.pay_min)}${suffix}`;
  }
  if (j.pay_raw) return j.pay_raw.length > 24 ? `${j.pay_raw.slice(0, 24)}…` : j.pay_raw;
  return "—";
}

export default async function AdminJobsPage({ searchParams }: PageProps) {
  const sp = await searchParams;

  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  const page = sp.page ? Math.max(1, parseInt(sp.page)) : 1;

  let data;
  try {
    data = await fetchAdminJobs(session.access_token, {
      q: sp.q,
      families: sp.families,
      industries: sp.industries,
      states: sp.states,
      city: sp.city,
      employment_types: sp.employment_types,
      sources: sp.sources,
      source_sites: sp.source_sites,
      status: sp.status,
      apply_link: sp.apply_link,
      has_pay: parseBool(sp.has_pay),
      pay_gte: sp.pay_gte ? Number(sp.pay_gte) : undefined,
      internal_apply: parseBool(sp.internal_apply),
      posted_from: sp.posted_from,
      posted_to: sp.posted_to,
      created_from: sp.created_from,
      created_to: sp.created_to,
      candidates: sp.candidates,
      sort: sp.sort,
      page,
      page_size: PAGE_SIZE,
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

  // Humanized source labels — the filter dropdown, active chips, and the
  // Source column all read the same words ("Employer import", never
  // "employer_import"); the raw values stay in the URL/API.
  const sourceOptions = data.facets.sources.map((s: string) => ({
    value: s,
    label: humanizeJobSource(s),
  }));

  const chipFields: FilterChipDef[] = [
    { param: "q", label: "Search" },
    { param: "families", label: "Family", multi: true, options: data.facets.families },
    { param: "industries", label: "Industry", multi: true },
    { param: "states", label: "State", multi: true },
    { param: "city", label: "City" },
    { param: "employment_types", label: "Type", multi: true },
    { param: "sources", label: "Source", multi: true, options: sourceOptions },
    { param: "source_sites", label: "Site", multi: true },
    { param: "status", label: "Status", options: STATUS_OPTIONS },
    { param: "apply_link", label: "Apply link", options: APPLY_LINK_OPTIONS },
    { param: "has_pay", label: "Pay", options: PAY_OPTIONS },
    { param: "pay_gte", label: "Pay at least" },
    ...(data.supports_internal_apply
      ? [{
          param: "internal_apply",
          label: "Internal apply",
          options: [
            { value: "true", label: "Enabled" },
            { value: "false", label: "Disabled" },
          ],
        }]
      : []),
    { param: "posted_from", label: "Posted from" },
    { param: "posted_to", label: "Posted to" },
    { param: "created_from", label: "Imported from" },
    { param: "created_to", label: "Imported to" },
    { param: "candidates", label: "Candidates", options: CANDIDATE_OPTIONS },
  ];
  const hasFilters = chipFields.some((f) => !!sp[f.param as keyof typeof sp]);
  const filterSentence = describeActiveFilters(sp as Record<string, string | undefined>, chipFields);

  const from = data.total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, data.total);
  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Jobs" }]} />
        <PageHeader
          eyebrow="Marketplace"
          title="Jobs"
          lead={
            hasFilters
              ? `${data.total} matching postings`
              : `${data.total} structured postings across the catalog`
          }
        />

        {/* Filter bar — 4 primary controls; long tail behind "More filters" */}
        <Reveal>
          <FilterBar
            footer={<ActiveFilterChips fields={chipFields} className="mt-3" />}
            moreParams={[
              "industries",
              "city",
              "employment_types",
              "status",
              "sources",
              "source_sites",
              "has_pay",
              "apply_link",
              "internal_apply",
              "candidates",
              "posted_from",
              "posted_to",
            ]}
            primary={
              <>
                <SearchSuggestField
                  param="q"
                  suggest="admin-jobs"
                  label="Search title or employer"
                  placeholder="Electrician, Southwire…"
                  className="flex-1 min-w-[200px]"
                  inputClassName="px-3 py-2 pl-9 text-body"
                />
                <UrlMultiSelectField
                  param="families"
                  label="Job family"
                  options={data.facets.families}
                  className="min-w-[180px]"
                />
                <UrlMultiSelectField
                  param="states"
                  label="State"
                  options={data.facets.states.map((s) => ({ value: s, label: s }))}
                  className="min-w-[110px]"
                />
                <UrlSelectField
                  param="sort"
                  label="Sort"
                  className="min-w-[120px]"
                  selectClassName="px-2 py-2 text-body"
                  options={[
                    { value: "", label: "Newest" },
                    { value: "posted", label: "Posted date" },
                    { value: "title", label: "Title" },
                    { value: "pay", label: "Pay" },
                  ]}
                />
              </>
            }
          >
            <FilterGroup label="Job details">
              <UrlMultiSelectField
                param="industries"
                label="Industry"
                options={data.facets.industries.map((i) => ({ value: i, label: i }))}
                className="min-w-[140px]"
              />
              <UrlSearchField
                param="city"
                label="City"
                placeholder="Carrollton…"
                className="min-w-[140px]"
                inputClassName="px-3 py-2 pl-9 text-body"
              />
              {data.facets.employment_types.length > 0 && (
                <UrlMultiSelectField
                  param="employment_types"
                  label="Employment type"
                  options={data.facets.employment_types.map((s) => ({ value: s, label: s.replace(/_/g, " ") }))}
                  className="min-w-[140px]"
                />
              )}
              <UrlSelectField
                param="has_pay"
                label="Pay info"
                className="min-w-[110px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...PAY_OPTIONS]}
              />
            </FilterGroup>
            <FilterGroup label="Source & health">
              <UrlSelectField
                param="status"
                label="Status"
                className="min-w-[130px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...STATUS_OPTIONS]}
              />
              <UrlMultiSelectField
                param="sources"
                label="Source"
                options={sourceOptions}
                className="min-w-[130px]"
              />
              <UrlMultiSelectField
                param="source_sites"
                label="Source site"
                options={data.facets.source_sites.map((s) => ({ value: s, label: s.replace(/_/g, " ") }))}
                className="min-w-[140px]"
              />
              <UrlSelectField
                param="apply_link"
                label="Apply link"
                className="min-w-[120px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...APPLY_LINK_OPTIONS]}
              />
              {data.supports_internal_apply && (
                <UrlSelectField
                  param="internal_apply"
                  label="Internal apply"
                  className="min-w-[120px]"
                  selectClassName="px-2 py-2 text-body"
                  options={[
                    { value: "", label: "Any" },
                    { value: "true", label: "Enabled" },
                    { value: "false", label: "Disabled" },
                  ]}
                />
              )}
            </FilterGroup>
            <FilterGroup label="Candidates & dates">
              <UrlSelectField
                param="candidates"
                label="Candidates"
                className="min-w-[140px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...CANDIDATE_OPTIONS]}
              />
              <UrlDateField param="posted_from" label="Posted from" className="min-w-[135px]" inputClassName="px-2 py-1.5 text-body" />
              <UrlDateField param="posted_to" label="Posted to" className="min-w-[135px]" inputClassName="px-2 py-1.5 text-body" />
            </FilterGroup>
          </FilterBar>
        </Reveal>

        {/* Results fade in ~150ms when a filter/search changes — no flash. */}
        <FilterTransition className="space-y-6">
        <p className="text-body text-slate" aria-live="polite">
          Showing {from}–{to} of {data.total}
          {hasFilters ? " matching jobs" : " jobs"}
        </p>

        {/* Results — one white sheet, hairline rows */}
        {data.jobs.length === 0 ? (
          <div className="rounded-[10px] border border-hairline bg-white p-8 text-center">
            <p className="text-ink font-medium">
              {hasFilters ? "No jobs match these filters" : "No jobs found"}
            </p>
            {hasFilters && (
              <p className="text-body text-slate mt-1">
                Active filters: {filterSentence || "none"}. Remove one, or clear all to widen the results.
              </p>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto rounded-[10px] border border-hairline bg-white">
            <table className="w-full min-w-[860px] text-body">
              <thead>
                <tr className="text-left text-caption text-slate-muted">
                  <th className="px-5 py-3 font-medium">Job</th>
                  <th className="px-3 py-3 font-medium">Location</th>
                  <th className="px-3 py-3 font-medium">Family</th>
                  <th className="px-3 py-3 font-medium">Pay</th>
                  <th className="px-3 py-3 font-medium">Source</th>
                  <th className="px-3 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 text-right font-medium">Candidates</th>
                </tr>
              </thead>
              <tbody>
                {data.jobs.map((j) => {
                  const location = [j.city, j.state].filter(Boolean).join(", ") || "—";
                  return (
                    <tr key={j.id} className="border-t border-hairline align-top">
                      <td className="px-5 py-3.5">
                        <span className="block font-medium text-cohere-ink">{j.title}</span>
                        {j.employer_id ? (
                          <Link
                            href={`/admin/employers/${j.employer_id}`}
                            className="text-caption text-slate hover:text-cohere-ink transition-colors"
                          >
                            {j.employer_name ?? "Unknown employer"}
                          </Link>
                        ) : (
                          <span className="text-caption text-slate">{j.employer_name ?? "—"}</span>
                        )}
                      </td>
                      <td className="px-3 py-3.5 text-slate">{location}</td>
                      <td className="px-3 py-3.5 text-slate">{j.family_name ?? "—"}</td>
                      <td className="px-3 py-3.5 text-slate tabular-nums">{formatPay(j)}</td>
                      <td className="px-3 py-3.5 text-slate">
                        {j.source ? humanizeJobSource(j.source) : "—"}
                        {j.source_site && (
                          <span className="block text-caption text-slate-muted">{j.source_site.replace(/_/g, " ")}</span>
                        )}
                      </td>
                      <td className="px-3 py-3.5">
                        <span
                          className={cn(
                            "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
                            // Semantic slots: stale = attention, active =
                            // positive, inactive = muted terminal.
                            j.is_stale
                              ? "border-studio-maroon bg-studio-maroon text-white"
                              : j.is_active
                                ? "border-cohere-green bg-cohere-green text-white"
                                : "border-hairline bg-stone/40 text-slate-muted",
                          )}
                        >
                          {j.is_stale ? "Stale" : j.is_active ? "Active" : "Inactive"}
                        </span>
                        {j.apply_link_status === "broken" && (
                          <span className="mt-1 block text-[11px] font-medium text-error-red">Broken link</span>
                        )}
                      </td>
                      <td className="px-5 py-3.5 text-right tabular-nums text-cohere-ink">{j.candidate_count}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {data.total > PAGE_SIZE && (
          <div className="flex flex-wrap items-center justify-between gap-3 text-caption text-slate">
            <span>
              Showing {from}–{to} of {data.total}
            </span>
            <div className="flex items-center gap-3">
              <PagerJump
                basePath="/admin/jobs"
                params={sp as Record<string, string | undefined>}
                page={page}
                totalPages={totalPages}
              />
              <div className="flex gap-2">
                {page > 1 && (
                  <Link
                    href={`/admin/jobs?${new URLSearchParams({ ...sp, page: String(page - 1) })}`}
                    className="btn-pill-outline"
                  >
                    Previous
                  </Link>
                )}
                {page < totalPages && (
                  <Link
                    href={`/admin/jobs?${new URLSearchParams({ ...sp, page: String(page + 1) })}`}
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
