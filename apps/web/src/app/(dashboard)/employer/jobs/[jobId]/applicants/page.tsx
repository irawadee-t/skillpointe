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

import { fetchJobApplicants } from "@/lib/api/employer";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { ApplicantMatchCard } from "@/components/employer/ApplicantMatchCard";
import { AIPriorityPanel } from "@/components/employer/AIPriorityPanel";

interface PageProps {
  params: Promise<{ jobId: string }>;
  searchParams: Promise<{
    eligibility?: string;
    min_score?: string;
    state?: string;
    relocate?: string;
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

  const backHref = role === "admin" ? "/admin/employers" : "/employer";

  let data;
  try {
    data = await fetchJobApplicants(jobId, token, {
      eligibility: eligibilityFilter,
      minScore,
      state: stateFilter,
      willingToRelocate: relocateFilter,
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      return (
        <main className="p-6 md:p-8">
          <div className="max-w-5xl mx-auto">
            <BackLink href={backHref} />
            <div className="mt-6 bg-rose-500/10 border border-rose-500/30 rounded-lg p-5 text-sm text-rose-400">
              Job not found or you do not have access to this job.
            </div>
          </div>
        </main>
      );
    }
    return (
      <main className="p-6 md:p-8">
        <div className="max-w-5xl mx-auto">
          <BackLink href={backHref} />
          <div className="mt-6 bg-rose-500/10 border border-rose-500/30 rounded-lg p-5 text-sm text-rose-400">
            <strong>Could not reach the API.</strong> The backend may be starting up — please refresh in a moment.
          </div>
        </div>
      </main>
    );
  }

  const hasActiveFilters =
    eligibilityFilter !== "all" || minScore > 0 || stateFilter || relocateFilter !== undefined;

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <BackLink href={backHref} />
          <div className="flex items-start justify-between mt-1">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-white">{data.job_title}</h1>
              <p className="text-sm text-zinc-400 mt-0.5">{data.employer_name}</p>
            </div>
            <Link
              href={`/employer/jobs/${jobId}/edit`}
              className="shrink-0 text-sm text-zinc-400 hover:text-white border border-zinc-700 rounded-lg px-3 py-1.5 hover:border-zinc-500 transition-colors"
            >
              Edit job
            </Link>
          </div>
        </div>

        {/* Quick stats */}
        <div className="grid grid-cols-3 gap-4">
          <StatCard label="Matched candidates" value={data.total_visible} />
          <StatCard label="Eligible" value={data.eligible_count} />
          <StatCard label="Near fit" value={data.near_fit_count} />
        </div>

        {/* AI prioritisation panel */}
        {data.applicants.length > 0 && (
          <AIPriorityPanel jobId={jobId} jobTitle={data.job_title} token={token} isAdmin={role === "admin"} />
        )}

        {/* Filter bar */}
        <FilterBar
          jobId={jobId}
          eligibility={eligibilityFilter}
          minScore={minScore}
          state={stateFilter}
          relocate={relocateFilter}
        />

        {/* Active filter indicator */}
        {hasActiveFilters && (
          <div className="flex items-center gap-2 text-sm text-zinc-400">
            <span>Filters active</span>
            <Link
              href={`/employer/jobs/${jobId}/applicants`}
              className="text-cyan-400 hover:text-cyan-300 font-medium transition-colors"
            >
              Clear all
            </Link>
          </div>
        )}

        {/* Matched candidates list */}
        {data.applicants.length === 0 ? (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center">
            <p className="text-zinc-300 font-medium">No matched candidates found</p>
            <p className="text-sm text-zinc-500 mt-2">
              {hasActiveFilters
                ? "Try adjusting your filters."
                : "Matches are computed when the admin runs the scoring pipeline."}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {data.applicants.map((match) => (
              <ApplicantMatchCard
                key={match.match_id}
                match={match}
                jobId={jobId}
                jobTitle={data.job_title}
                token={token}
                isAdmin={role === "admin"}
              />
            ))}
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
      className="text-sm text-zinc-400 hover:text-white inline-flex items-center gap-1 transition-colors"
    >
      ← Back to dashboard
    </Link>
  );
}

function StatCard({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 text-center">
      <div className="text-3xl font-bold text-cyan-400">{value}</div>
      <div className="text-xs text-zinc-500 mt-1">{label}</div>
    </div>
  );
}

/**
 * Filter bar — renders as a GET form so filters are reflected in the URL
 * and the page can be bookmarked / shared.
 */
function FilterBar({
  jobId,
  eligibility,
  minScore,
  state,
  relocate,
}: {
  jobId: string;
  eligibility: string;
  minScore: number;
  state: string | undefined;
  relocate: boolean | undefined;
}) {
  return (
    <form
      method="GET"
      action={`/employer/jobs/${jobId}/applicants`}
      className="bg-zinc-900 border border-zinc-800 rounded-lg p-4"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500 mb-3">
        Filters
      </p>
      <div className="flex flex-wrap gap-4 items-end">
        {/* Eligibility */}
        <div className="min-w-[140px]">
          <label className="block text-xs text-zinc-400 mb-1">Eligibility</label>
          <select
            name="eligibility"
            defaultValue={eligibility}
            className="w-full border border-zinc-700 rounded-md px-2 py-1.5 text-sm bg-zinc-900 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
          >
            <option value="all">All (eligible + near fit)</option>
            <option value="eligible">Eligible only</option>
            <option value="near_fit">Near fit only</option>
          </select>
        </div>

        {/* Min score */}
        <div className="min-w-[120px]">
          <label className="block text-xs text-zinc-400 mb-1">Min score</label>
          <input
            type="number"
            name="min_score"
            min="0"
            max="100"
            step="5"
            defaultValue={minScore || ""}
            placeholder="0"
            className="w-full border border-zinc-700 rounded-md px-2 py-1.5 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
          />
        </div>

        {/* State */}
        <div className="min-w-[100px]">
          <label className="block text-xs text-zinc-400 mb-1">State</label>
          <input
            type="text"
            name="state"
            maxLength={2}
            defaultValue={state || ""}
            placeholder="e.g. TX"
            className="w-full border border-zinc-700 rounded-md px-2 py-1.5 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 uppercase focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
          />
        </div>

        {/* Willing to relocate */}
        <div className="min-w-[140px]">
          <label className="block text-xs text-zinc-400 mb-1">Relocate willingness</label>
          <select
            name="relocate"
            defaultValue={
              relocate === true ? "true" : relocate === false ? "false" : ""
            }
            className="w-full border border-zinc-700 rounded-md px-2 py-1.5 text-sm bg-zinc-900 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
          >
            <option value="">Any</option>
            <option value="true">Open to relocate</option>
            <option value="false">Local only</option>
          </select>
        </div>

        <button
          type="submit"
          className="px-4 py-1.5 bg-cyan-500 text-black text-sm font-medium rounded-full hover:bg-cyan-400 transition-colors"
        >
          Apply
        </button>
      </div>
    </form>
  );
}
