/**
 * Ranked applicants per job — Phase 6.2
 *
 * Shows ranked applicant list for a specific job with:
 *   - Job header (title, counts, link back to dashboard)
 *   - Filter controls (eligibility, min score, state, relocate)
 *   - ApplicantMatchCard per match, ordered by policy_adjusted_score DESC
 *   - Empty state handling
 *
 * Visibility enforced: only applicants matched to employer's OWN job
 * with is_visible_to_employer=TRUE are returned by the API.
 *
 * Server component. Filters are read from URL search params.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { fetchJobApplicants } from "@/lib/api/employer";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { ApplicantMatchCard } from "@/components/employer/ApplicantMatchCard";
import { JobPreviewTrigger } from "@/components/jobs/JobPreviewDialog";
import { AIPriorityPanel } from "@/components/employer/AIPriorityPanel";
import { Card, MetricCard, MonoLabel, Stagger, StaggerItem } from "@/components/ui";
import { FilterBarClient } from "./FilterBarClient";

interface PageProps {
  params: Promise<{ jobId: string }>;
  searchParams: Promise<{
    eligibility?: string;
    min_score?: string;
    state?: string;
    relocate?: string;
    q?: string;
    page?: string;
  }>;
}

export default async function JobApplicantsPage({
  params,
  searchParams,
}: PageProps) {
  const { jobId } = await params;
  const sp = await searchParams;

  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const role = session.user.app_metadata?.role as string;
  if (role !== "employer" && role !== "admin") redirect("/login");

  const token = session.access_token;

  // Parse filters from URL
  const eligibilityFilter =
    sp.eligibility === "eligible" || sp.eligibility === "near_fit"
      ? sp.eligibility
      : "all";
  const minScore = sp.min_score ? Number(sp.min_score) : 0;
  const stateFilter = sp.state || undefined;
  const relocateFilter =
    sp.relocate === "true" ? true : sp.relocate === "false" ? false : undefined;
  const currentPage = sp.page ? Math.max(1, parseInt(sp.page, 10) || 1) : 1;

  const backHref = role === "admin" ? "/admin/employers" : "/employer";

  let data;
  try {
    data = await fetchJobApplicants(jobId, token, {
      eligibility: eligibilityFilter,
      minScore,
      state: stateFilter,
      willingToRelocate: relocateFilter,
      q: sp.q || undefined,
      page: currentPage,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      return (
        <main className="py-8">
          <div className="page-shell">
            <BackLink href={backHref} />
            <div className="mt-6 rounded-md border border-error-red/30 bg-rose-50 p-5 text-body text-error-red">
              Job not found or you do not have access to this job.
            </div>
          </div>
        </main>
      );
    }
    return (
      <main className="py-8">
        <div className="page-shell">
          <BackLink href={backHref} />
          <div className="mt-6 rounded-md border border-error-red/30 bg-rose-50 p-5 text-body text-error-red">
            <strong className="font-medium">Could not reach the API.</strong> The backend may be starting up. Please refresh in a moment.
          </div>
        </div>
      </main>
    );
  }

  const hasActiveFilters =
    eligibilityFilter !== "all" || minScore > 0 || stateFilter || relocateFilter !== undefined || !!sp.q;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        {/* Header */}
        <div>
          <BackLink href={backHref} />
          <div className="flex items-start justify-between gap-4 mt-3 border-b border-hairline pb-8">
            <div>
              <MonoLabel className="mb-3 block">Matched candidates</MonoLabel>
              <h1 className="font-display text-card sm:text-heading text-cohere-ink">{data.job_title}</h1>
              <p className="text-body-lg text-slate mt-3">{data.employer_name}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <JobPreviewTrigger
                jobId={jobId}
                jobTitle={data.job_title}
                meta={data.employer_name}
                token={token}
                label="View job"
              />
              <Link
                href={`/employer/jobs/${jobId}/edit`}
                className="btn-pill-outline shrink-0"
              >
                Edit job
              </Link>
            </div>
          </div>
        </div>

        {/* Quick stats */}
        <Stagger className="grid grid-cols-3 gap-4">
          <StaggerItem><MetricCard label="Matched candidates" value={data.total_visible} /></StaggerItem>
          <StaggerItem><MetricCard label="Eligible" value={data.eligible_count} /></StaggerItem>
          <StaggerItem><MetricCard label="Near fit" value={data.near_fit_count} tone="stone" /></StaggerItem>
        </Stagger>

        {/* AI prioritization panel */}
        {data.applicants.length > 0 && (
          <AIPriorityPanel jobId={jobId} jobTitle={data.job_title} token={token} isAdmin={role === "admin"} />
        )}

        {/* Filter bar */}
        <FilterBarClient
          jobId={jobId}
          eligibility={eligibilityFilter}
          minScore={minScore}
          state={stateFilter}
          relocate={relocateFilter}
        />

        {/* Active filter indicator */}
        {hasActiveFilters && (
          <div className="flex items-center gap-2 text-body text-slate">
            <span>Filters active</span>
            <Link
              href={`/employer/jobs/${jobId}/applicants`}
              className="text-cohere-blue hover:opacity-70 font-medium transition-opacity"
            >
              Clear all
            </Link>
          </div>
        )}

        {/* Matched candidates list */}
        {data.applicants.length === 0 ? (
          <Card tone="stone" className="p-10 text-center">
            <p className="text-body-lg font-medium text-ink">
              {sp.q ? <>No results for &ldquo;{sp.q}&rdquo;</> : hasActiveFilters ? "No matched candidates found" : "No matches yet"}
            </p>
            <p className="text-body text-slate mt-2">
              {hasActiveFilters
                ? "Try adjusting your filters."
                : "Matches usually appear within 24h of posting."}
            </p>
            {!hasActiveFilters && (
              <a
                href="mailto:admin@skillpointe.com?subject=No matches for job"
                className="mt-3 inline-flex items-center gap-1 text-body font-medium text-cohere-blue hover:opacity-70 transition-opacity"
              >
                Contact admin if it&apos;s been longer
              </a>
            )}
          </Card>
        ) : (
          <Stagger className="space-y-4">
            {data.applicants.map((match) => (
              <StaggerItem key={match.match_id}>
                <ApplicantMatchCard
                  match={match}
                  jobId={jobId}
                  jobTitle={data.job_title}
                  token={token}
                  isAdmin={role === "admin"}
                />
              </StaggerItem>
            ))}
          </Stagger>
        )}

        {/* Pagination — server-side, filter state carried through the links */}
        {data.total_pages > 1 && (
          <div className="flex items-center justify-between rounded-md border border-border-light bg-white px-4 py-3">
            <p className="text-body text-slate">
              Page {data.page} of {data.total_pages} ({data.filtered_total.toLocaleString()}{" "}
              {data.filtered_total === 1 ? "candidate" : "candidates"})
            </p>
            <div className="flex gap-2">
              {data.page > 1 && (
                <ApplicantsPageLink jobId={jobId} sp={sp} page={data.page - 1} label="Previous" icon="left" />
              )}
              {data.page < data.total_pages && (
                <ApplicantsPageLink jobId={jobId} sp={sp} page={data.page + 1} label="Next" icon="right" />
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function BackLink({ href }: { href: string }) {
  return (
    <Link
      href={href}
      className="mono-label inline-flex items-center gap-1 text-slate hover:text-ink transition-colors"
    >
      ← Back to dashboard
    </Link>
  );
}

function ApplicantsPageLink({
  jobId,
  sp,
  page,
  label,
  icon,
}: {
  jobId: string;
  sp: { eligibility?: string; min_score?: string; state?: string; relocate?: string; q?: string };
  page: number;
  label: string;
  icon: "left" | "right";
}) {
  const qs = new URLSearchParams();
  if (sp.eligibility) qs.set("eligibility", sp.eligibility);
  if (sp.min_score) qs.set("min_score", sp.min_score);
  if (sp.state) qs.set("state", sp.state);
  if (sp.relocate) qs.set("relocate", sp.relocate);
  if (sp.q) qs.set("q", sp.q);
  if (page > 1) qs.set("page", String(page));
  const query = qs.toString();
  return (
    <Link
      href={`/employer/jobs/${jobId}/applicants${query ? `?${query}` : ""}`}
      className="flex items-center gap-1 rounded-pill border border-hairline px-3 py-1.5 text-caption text-slate transition-colors hover:border-cohere-ink hover:text-ink"
    >
      {icon === "left" && <ChevronLeft className="h-3.5 w-3.5" />}
      {label}
      {icon === "right" && <ChevronRight className="h-3.5 w-3.5" />}
    </Link>
  );
}

