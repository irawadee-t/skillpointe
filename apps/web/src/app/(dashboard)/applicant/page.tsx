/**
 * Applicant dashboard — Phase 6.1
 *
 * Shows:
 *   - Profile summary (name, program, location, geography prefs, completeness)
 *   - Match summary counts (eligible + near_fit)
 *   - Links to ranked job views
 *
 * Server component: fetches data server-side using the Supabase session token.
 */
import Link from "next/link";
import { redirect } from "next/navigation";

import { fetchMyMatches, fetchMyProfile } from "@/lib/api/applicant";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";

export default async function ApplicantDashboard() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const role = session.user.app_metadata?.role;
  if (role !== "applicant") redirect("/login");

  const token = session.access_token;

  // Fetch profile and match counts in parallel
  const [profile, matches] = await Promise.all([
    fetchMyProfile(token).catch((e) => {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }),
    fetchMyMatches(token).catch(() => null),
  ]);

  async function signOut() {
    "use server";
    const supabase = await createClient();
    await supabase.auth.signOut();
    redirect("/login");
  }

  return (
    <main className="min-h-screen bg-gray-50 p-6 md:p-8">
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Welcome back
              {profile?.first_name ? `, ${profile.first_name}` : ""}
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">{session.user.email}</p>
          </div>
          <form action={signOut}>
            <button
              type="submit"
              className="text-sm text-gray-500 hover:text-red-600 underline"
            >
              Sign out
            </button>
          </form>
        </div>

        {/* Profile not linked warning */}
        {!profile && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
            <strong>Profile not yet linked.</strong> Your account hasn&apos;t
            been connected to an applicant profile. Contact a SkillPointe admin
            to link your account.
          </div>
        )}

        {/* Profile summary card */}
        {profile && (
          <section className="bg-white border border-gray-200 rounded-lg p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-gray-900">Your profile</h2>
              <ProfileCompletenessChip score={profile.profile_completeness} />
            </div>

            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
              <ProfileField
                label="Program / trade"
                value={
                  profile.canonical_job_family_code
                    ? `${profile.program_name_raw ?? ""} (${profile.canonical_job_family_code})`
                    : (profile.program_name_raw ?? null)
                }
                fallback="Not normalised yet"
              />
              <ProfileField
                label="Location"
                value={
                  [profile.city, profile.state].filter(Boolean).join(", ") ||
                  null
                }
                fallback="Not set"
              />
              <ProfileField
                label="Availability"
                value={
                  profile.available_from_date ??
                  profile.expected_completion_date ??
                  null
                }
                fallback="Not set"
              />
              <ProfileField
                label="Preferences"
                value={
                  [
                    profile.willing_to_relocate ? "Open to relocate" : null,
                    profile.willing_to_travel ? "Open to travel" : null,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "No relocation / travel"
                }
              />
            </dl>

            {!profile.canonical_job_family_code && (
              <p className="mt-4 text-xs text-amber-600">
                ⚠ Your trade/program hasn&apos;t been matched to a job family
                yet. Match quality will improve after admin normalises your
                data.
              </p>
            )}
          </section>
        )}

        {/* Match summary */}
        {matches && (
          <section>
            <h2 className="font-semibold text-gray-900 mb-3">Your matches</h2>

            {!matches.has_matches ? (
              <NoMatchesState
                profileHasFamily={matches.profile_has_family}
                profileHasLocation={matches.profile_has_location}
              />
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <MatchSummaryCard
                  label="Best immediate opportunities"
                  sublabel="Eligible matches"
                  count={matches.total_eligible}
                  color="green"
                  href="/applicant/matches"
                />
                <MatchSummaryCard
                  label="Promising near-fit opportunities"
                  sublabel="Near-fit matches"
                  count={matches.total_near_fit}
                  color="orange"
                  href="/applicant/matches#near-fit"
                />
              </div>
            )}

            {matches.has_matches && (
              <div className="mt-4">
                <Link
                  href="/applicant/matches"
                  className="inline-flex items-center text-sm font-medium text-blue-600 hover:text-blue-800"
                >
                  View all ranked jobs →
                </Link>
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ProfileField({
  label,
  value,
  fallback = "—",
}: {
  label: string;
  value: string | null | undefined;
  fallback?: string;
}) {
  return (
    <div>
      <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide">
        {label}
      </dt>
      <dd
        className={`mt-0.5 ${value ? "text-gray-900" : "text-gray-400 italic"}`}
      >
        {value ?? fallback}
      </dd>
    </div>
  );
}

function ProfileCompletenessChip({ score }: { score: number }) {
  const color =
    score >= 80
      ? "text-green-700 bg-green-50 border-green-200"
      : score >= 50
        ? "text-amber-700 bg-amber-50 border-amber-200"
        : "text-red-700 bg-red-50 border-red-200";
  return (
    <span
      className={`text-xs font-medium border rounded-full px-2.5 py-1 ${color}`}
    >
      Profile {score}% complete
    </span>
  );
}

function MatchSummaryCard({
  label,
  sublabel,
  count,
  color,
  href,
}: {
  label: string;
  sublabel: string;
  count: number;
  color: "green" | "orange";
  href: string;
}) {
  const border =
    color === "green" ? "border-green-200" : "border-orange-200";
  const countColor =
    color === "green" ? "text-green-700" : "text-orange-700";

  return (
    <Link
      href={href}
      className={`bg-white border ${border} rounded-lg p-4 hover:shadow-sm transition-shadow block`}
    >
      <div className={`text-3xl font-bold ${countColor}`}>{count}</div>
      <div className="text-sm font-medium text-gray-900 mt-1">{label}</div>
      <div className="text-xs text-gray-500 mt-0.5">{sublabel}</div>
    </Link>
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
    <div className="bg-white border border-gray-200 rounded-lg p-6 text-center">
      <p className="text-gray-600 font-medium">No matches yet</p>
      <p className="text-sm text-gray-500 mt-2">
        Matches are computed when the admin runs the scoring pipeline.
      </p>
      {!profileHasFamily && (
        <p className="text-xs text-amber-600 mt-3">
          ⚠ Your trade/program is not yet normalised — this affects match
          quality.
        </p>
      )}
      {!profileHasLocation && (
        <p className="text-xs text-amber-600 mt-1">
          ⚠ Your location is not set — geography-based matching is limited.
        </p>
      )}
    </div>
  );
}
