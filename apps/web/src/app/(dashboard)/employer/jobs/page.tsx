/**
 * Employer Jobs List — /employer/jobs
 *
 * The employer's own postings with the same granular filter bar as the admin
 * jobs console, scoped server-side to this employer's rows only (isolation is
 * enforced in the API — filters can never widen visibility).
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { Plus, Users, Edit3 } from "lucide-react";

import { fetchMyJobs, formatWorkSetting } from "@/lib/api/employer";
import { humanizeJobSource } from "@/lib/humanize";
import { JobPreviewTrigger } from "@/components/jobs/JobPreviewDialog";
import JobLifecycleActions from "./JobLifecycleActions";
import { statusChipClass, ATTENTION_TEXT_CLASS } from "@/components/ui/statusTones";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import {
  PageHeader,
  Reveal,
  Stagger,
  StaggerItem,
  UrlSearchField,
  UrlSelectField,
  UrlMultiSelectField,
  UrlDateField,
  ActiveFilterChips,
  describeActiveFilters,
  type FilterChipDef,
} from "@/components/ui";

interface PageProps {
  searchParams: Promise<{
    q?: string;
    families?: string;
    states?: string;
    city?: string;
    sources?: string;
    status?: string;
    apply_link?: string;
    has_pay?: string;
    posted_from?: string;
    posted_to?: string;
    candidates?: string;
    sort?: string;
  }>;
}

const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "filled", label: "Filled" },
  { value: "closed", label: "Closed" },
  { value: "inactive", label: "Hidden (any reason)" },
  { value: "stale", label: "Stale (60+ days unverified)" },
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

const COUNT_LEGEND =
  "Eligible = meets all requirements now · Near fit = close with small gaps";

/** Compact relative time for the freshness line ("2h ago", "3d ago"). */
function relTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.max(0, Math.floor(ms / 60_000));
  if (mins < 60) return mins <= 1 ? "just now" : `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/**
 * Career-source freshness line — only for jobs whose posting URL is tracked
 * by a connected careers source. Honest either way: still on the site (and
 * when we last checked), or exactly when it disappeared.
 */
function SourceFreshness({
  lastSeenAt, vanishedAt,
}: { lastSeenAt: string | null; vanishedAt: string | null }) {
  if (vanishedAt) {
    const when = new Date(vanishedAt).toLocaleDateString("en-US", {
      month: "short", day: "numeric",
    });
    return (
      <p className={`text-micro font-medium mt-1 ${ATTENTION_TEXT_CLASS}`}>
        No longer on your careers site. Unpublished {when}
      </p>
    );
  }
  if (!lastSeenAt) return null;
  return (
    <p className="text-micro text-slate-muted mt-1">
      On your careers site · checked {relTime(lastSeenAt)}
    </p>
  );
}

/**
 * Eligible / near-fit counts with honest semantics. When near-fits are ≥50%
 * of everyone visible (the number stops meaning anything), we show a
 * "top N near fits" link into the ranked list instead of the raw count.
 */
function MatchCounts({
  eligible, nearFit, totalVisible, applicantsHref,
}: {
  eligible: number; nearFit: number; totalVisible: number; applicantsHref: string;
}) {
  const total = totalVisible || eligible + nearFit;
  const nearFitIsNoise = total > 0 && nearFit * 2 >= total && nearFit >= 10;
  return (
    <p className="shrink-0 text-right text-body text-slate" title={COUNT_LEGEND}>
      <span className="font-medium text-cohere-ink tabular-nums">{eligible}</span> eligible
      <span className="mx-1.5 text-slate-muted">·</span>
      {nearFitIsNoise ? (
        <Link
          href={applicantsHref}
          className="font-medium text-cohere-blue hover:opacity-70 transition-opacity"
        >
          top {Math.min(nearFit, 10)} near fits
        </Link>
      ) : (
        <>
          <span className="font-medium text-cohere-ink tabular-nums">{nearFit}</span> near fit
        </>
      )}
    </p>
  );
}

export default async function EmployerJobsPage({ searchParams }: PageProps) {
  const sp = await searchParams;

  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role === "admin") redirect("/admin/jobs");
  if (role !== "employer") redirect("/login");
  const token = session.access_token;

  let data;
  try {
    data = await fetchMyJobs(session.access_token, {
      q: sp.q,
      families: sp.families,
      states: sp.states,
      city: sp.city,
      sources: sp.sources,
      status: sp.status,
      apply_link: sp.apply_link,
      has_pay: parseBool(sp.has_pay),
      posted_from: sp.posted_from,
      posted_to: sp.posted_to,
      candidates: sp.candidates,
      sort: sp.sort,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) redirect("/employer/onboarding");
    return (
      <main className="py-8">
        <div className="page-shell bg-cohere-coral/10 border border-cohere-coral-soft rounded-md p-5 text-body text-cohere-ink">
          {e instanceof ApiError ? `API error ${e.status}` : "Could not reach the API. Please refresh."}
        </div>
      </main>
    );
  }

  const chipFields: FilterChipDef[] = [
    { param: "q", label: "Search" },
    { param: "families", label: "Family", multi: true, options: data.facets.families },
    { param: "states", label: "State", multi: true },
    { param: "city", label: "City" },
    {
      param: "sources",
      label: "Source",
      multi: true,
      options: data.facets.sources.map((s) => ({ value: s, label: humanizeJobSource(s) })),
    },
    { param: "status", label: "Status", options: STATUS_OPTIONS },
    { param: "has_pay", label: "Pay", options: PAY_OPTIONS },
    { param: "posted_from", label: "Posted from" },
    { param: "posted_to", label: "Posted to" },
    { param: "candidates", label: "Candidates", options: CANDIDATE_OPTIONS },
  ];
  const hasFilters = chipFields.some((f) => !!sp[f.param as keyof typeof sp]);
  const filterSentence = describeActiveFilters(sp as Record<string, string | undefined>, chipFields);
  const unfiltered = data.unfiltered_total ?? data.total_jobs;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Employer workspace"
          title="Your jobs"
          lead={`${unfiltered} posting${unfiltered === 1 ? "" : "s"} for ${data.company_name}`}
          actions={
            <Link href="/employer/jobs/new" className="btn-primary">
              <Plus className="w-4 h-4" /> New job
            </Link>
          }
        />

        {/* Filter bar — same pattern as the admin console, scoped to your jobs */}
        <Reveal>
          <div className="rounded-[10px] border border-hairline bg-white p-4" data-tour-id="jobs-filters">
            <div className="flex flex-wrap gap-3 items-end">
              <UrlSearchField
                param="q"
                label="Search title"
                placeholder="Electrician…"
                className="flex-1 min-w-[180px]"
                inputClassName="px-3 py-2 pl-9 text-body"
              />
              <UrlMultiSelectField
                param="families"
                label="Job family"
                options={data.facets.families}
                className="min-w-[170px]"
              />
              <UrlMultiSelectField
                param="states"
                label="State"
                options={data.facets.states.map((s) => ({ value: s, label: s }))}
                className="min-w-[110px]"
              />
              <UrlSearchField
                param="city"
                label="City"
                placeholder="Carrollton…"
                className="min-w-[130px]"
                inputClassName="px-3 py-2 pl-9 text-body"
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
            </div>
            <div className="mt-3 flex flex-wrap gap-3 items-end border-t border-hairline pt-3">
              <UrlSelectField
                param="status"
                label="Status"
                className="min-w-[130px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...STATUS_OPTIONS]}
              />
              {data.facets.sources.length > 1 && (
                <UrlMultiSelectField
                  param="sources"
                  label="Source"
                  options={data.facets.sources.map((s) => ({ value: s, label: humanizeJobSource(s) }))}
                  className="min-w-[130px]"
                />
              )}
              <UrlSelectField
                param="has_pay"
                label="Pay info"
                className="min-w-[110px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...PAY_OPTIONS]}
              />
              <UrlSelectField
                param="candidates"
                label="Candidates"
                className="min-w-[140px]"
                selectClassName="px-2 py-2 text-body"
                options={[{ value: "", label: "Any" }, ...CANDIDATE_OPTIONS]}
              />
              <UrlDateField param="posted_from" label="Posted from" className="min-w-[135px]" inputClassName="px-2 py-1.5 text-body" />
              <UrlDateField param="posted_to" label="Posted to" className="min-w-[135px]" inputClassName="px-2 py-1.5 text-body" />
            </div>
            <ActiveFilterChips fields={chipFields} className="mt-3" />
          </div>
        </Reveal>

        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-body text-slate" aria-live="polite">
            Showing {data.total_jobs} of {unfiltered} job{unfiltered === 1 ? "" : "s"}
          </p>
          <p className="text-micro text-slate-muted">
            Eligible = meets all requirements now · Near fit = close with small gaps
          </p>
        </div>

        {data.jobs.length === 0 ? (
          <div className="rounded-[10px] border border-hairline bg-white p-10 text-center" data-tour-id="jobs-list">
            <p className="text-body-lg font-medium text-ink">
              {hasFilters ? "No jobs match these filters" : "No jobs yet"}
            </p>
            <p className="text-body text-slate mt-2">
              {hasFilters
                ? `Active filters: ${filterSentence || "none"}. Remove one, or clear all to widen the results.`
                : "Create your first job posting to start receiving ranked applicant matches."}
            </p>
          </div>
        ) : (
          <div data-tour-id="jobs-list">
          <Stagger className="space-y-4">
            {data.jobs.map((job) => {
              const locationStr = [job.city, job.state].filter(Boolean).join(", ");
              return (
                <StaggerItem
                  key={job.job_id}
                  className="rounded-[14px] border border-hairline bg-white p-6 transition-[color,background-color,border-color,box-shadow] duration-200 ease-cohere hover:shadow-float"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-[1.0625rem] font-medium text-cohere-ink leading-tight">
                          {job.title}
                        </h3>
                        {job.is_stale && (
                          <span className={statusChipClass("attention")}>Stale</span>
                        )}
                        {job.apply_link_status === "broken" && (
                          <span className="text-[11px] font-medium text-error-red">Broken apply link</span>
                        )}
                      </div>
                      <p className="text-body text-slate mt-1">
                        {locationStr || "Location not set"}
                        {job.work_setting && `, ${formatWorkSetting(job.work_setting)}`}
                        {job.family_name && ` · ${job.family_name}`}
                        {job.pay_raw && ` · ${job.pay_raw}`}
                      </p>
                      <SourceFreshness
                        lastSeenAt={job.source_last_seen_at}
                        vanishedAt={job.source_vanished_at}
                      />
                    </div>
                    <div className="flex shrink-0 items-center gap-4">
                      <MatchCounts
                        eligible={job.eligible_count}
                        nearFit={job.near_fit_count}
                        totalVisible={job.total_visible}
                        applicantsHref={`/employer/jobs/${job.job_id}/applicants`}
                      />
                      {/* Status chip + Pause / Fill / Close / Reopen / Delete
                          quick actions — optimistic with real undo. */}
                      <JobLifecycleActions
                        token={token}
                        jobId={job.job_id}
                        jobTitle={job.title}
                        initialStatus={job.status}
                        hasActivity={job.has_activity}
                      />
                    </div>
                  </div>

                  <div className="flex items-center gap-5 mt-5 pt-4 border-t border-hairline">
                    <Link
                      href={`/employer/jobs/${job.job_id}/applicants`}
                      className="inline-flex items-center gap-1.5 text-body font-medium text-cohere-blue hover:opacity-70 transition-opacity"
                    >
                      <Users className="w-3.5 h-3.5" /> View matched candidates ({job.total_visible})
                    </Link>
                    <Link
                      href={`/employer/jobs/${job.job_id}/edit`}
                      className="inline-flex items-center gap-1.5 text-body text-slate hover:text-ink transition-colors"
                    >
                      <Edit3 className="w-3.5 h-3.5" /> Edit
                    </Link>
                    {/* Opens the job-description popup — no navigation */}
                    <JobPreviewTrigger
                      jobId={job.job_id}
                      jobTitle={job.title}
                      meta={[locationStr || null, job.pay_raw].filter(Boolean).join(" · ") || data.company_name}
                      token={token}
                      variant="quiet"
                      label="Preview"
                    />
                  </div>
                </StaggerItem>
              );
            })}
          </Stagger>
          </div>
        )}
      </div>
    </main>
  );
}
