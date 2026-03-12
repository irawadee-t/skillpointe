/**
 * Ranked jobs list — Phase 6.1
 *
 * Two labeled sections:
 *   1. "Best immediate opportunities"  — eligible matches
 *   2. "Promising near-fit opportunities" — near_fit matches
 *
 * Server component: fetches data server-side.
 */
import Link from "next/link";
import { redirect } from "next/navigation";

import { fetchMyMatches } from "@/lib/api/applicant";
import { createClient } from "@/lib/supabase/server";
import { JobMatchCard } from "@/components/matches/JobMatchCard";

export default async function MatchesPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "applicant") redirect("/login");

  const token = session.access_token;
  let matches;
  try {
    matches = await fetchMyMatches(token);
  } catch {
    return (
      <main className="min-h-screen bg-gray-50 p-6 md:p-8">
        <div className="max-w-3xl mx-auto">
          <BackLink />
          <div className="mt-6 bg-red-50 border border-red-200 rounded-lg p-5 text-sm text-red-800">
            Failed to load your matches. Please try again or contact support.
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50 p-6 md:p-8">
      <div className="max-w-3xl mx-auto space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <BackLink />
            <h1 className="text-2xl font-bold text-gray-900 mt-1">Your job matches</h1>
          </div>
        </div>

        {!matches.has_matches ? (
          <NoMatchesState
            profileHasFamily={matches.profile_has_family}
            profileHasLocation={matches.profile_has_location}
          />
        ) : (
          <>
            {/* Section 1 — Eligible */}
            <section id="eligible">
              <SectionHeader
                title="Best immediate opportunities"
                subtitle="You meet the key requirements for these roles."
                count={matches.total_eligible}
                color="green"
              />
              {matches.eligible_matches.length === 0 ? (
                <EmptySectionState message="No eligible matches found yet." />
              ) : (
                <div className="space-y-4 mt-4">
                  {matches.eligible_matches.map((match) => (
                    <JobMatchCard key={match.match_id} match={match} />
                  ))}
                </div>
              )}
            </section>

            {/* Section 2 — Near fit */}
            <section id="near-fit">
              <SectionHeader
                title="Promising near-fit opportunities"
                subtitle="You're close — these roles have one or two gaps you can address."
                count={matches.total_near_fit}
                color="orange"
              />
              {matches.near_fit_matches.length === 0 ? (
                <EmptySectionState message="No near-fit matches found yet." />
              ) : (
                <div className="space-y-4 mt-4">
                  {matches.near_fit_matches.map((match) => (
                    <JobMatchCard key={match.match_id} match={match} />
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function BackLink() {
  return (
    <Link
      href="/applicant"
      className="text-sm text-gray-500 hover:text-gray-700 inline-flex items-center gap-1"
    >
      ← Back to dashboard
    </Link>
  );
}

function SectionHeader({
  title,
  subtitle,
  count,
  color,
}: {
  title: string;
  subtitle: string;
  count: number;
  color: "green" | "orange";
}) {
  const countColor = color === "green" ? "text-green-700" : "text-orange-700";
  return (
    <div className="flex items-start justify-between">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
        <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>
      </div>
      <span className={`text-2xl font-bold ${countColor} shrink-0 ml-4`}>{count}</span>
    </div>
  );
}

function EmptySectionState({ message }: { message: string }) {
  return (
    <div className="mt-4 bg-white border border-gray-200 rounded-lg p-5 text-sm text-gray-500 text-center">
      {message}
    </div>
  );
}

function NoMatchesState({
  profileHasFamily,
  profileHasLocation,
}: {
  profileHasFamily: boolean;
  profileHasLocation: boolean;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-8 text-center">
      <p className="text-gray-700 font-medium text-lg">No matches yet</p>
      <p className="text-sm text-gray-500 mt-2">
        Matches are computed when the admin runs the scoring pipeline.
      </p>
      {!profileHasFamily && (
        <p className="text-xs text-amber-600 mt-4">
          ⚠ Your trade/program is not yet normalised — this affects match quality.
        </p>
      )}
      {!profileHasLocation && (
        <p className="text-xs text-amber-600 mt-2">
          ⚠ Your location is not set — geography-based matching is limited.
        </p>
      )}
    </div>
  );
}
