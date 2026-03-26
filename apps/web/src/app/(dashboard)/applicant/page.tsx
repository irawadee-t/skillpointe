import Link from "next/link";
import { redirect } from "next/navigation";
import {
  User,
  MapPin,
  Calendar,
  Briefcase,
  ChevronRight,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
} from "lucide-react";

import { fetchMyMatches, fetchMyProfile } from "@/lib/api/applicant";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";

export default async function ApplicantDashboard() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();

  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "applicant") redirect("/login");

  const token = session.access_token;

  let profileMissing = false;
  const profile = await fetchMyProfile(token).catch((e) => {
    if (e instanceof ApiError && e.status === 404) { profileMissing = true; return null; }
    return null; // API unreachable — render error state below
  });

  if (profileMissing) redirect("/applicant/setup");
  if (!profile) return (
    <main className="p-6 md:p-8">
      <div className="max-w-3xl mx-auto bg-red-50 border border-red-200 rounded-xl p-5 text-sm text-red-800">
        <strong>Could not reach the API.</strong> The backend may be starting up — please refresh in a moment.
      </div>
    </main>
  );

  const matches = await fetchMyMatches(token).catch(() => null);

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-spf-navy">
            {profile?.first_name ? `Welcome back, ${profile.first_name}` : "Dashboard"}
          </h1>
          <Link
            href="/applicant/profile"
            className="text-sm font-medium text-spf-navy hover:text-spf-navy-light transition-colors flex items-center gap-1"
          >
            Edit profile <ChevronRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Profile card */}
        {profile && (
          <section className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
              <h2 className="font-semibold text-gray-900 text-sm">Profile overview</h2>
              <CompletenessBar score={profile.profile_completeness} />
            </div>
            <div className="px-6 py-5 grid grid-cols-1 sm:grid-cols-2 gap-5">
              <ProfileItem
                icon={<Briefcase className="w-4 h-4 text-spf-navy" />}
                label="Program"
                value={profile.canonical_job_family_code
                  ? `${profile.program_name_raw ?? ""} (${profile.canonical_job_family_code})`
                  : (profile.program_name_raw ?? null)}
                fallback="Not set"
              />
              <ProfileItem
                icon={<MapPin className="w-4 h-4 text-spf-navy" />}
                label="Location"
                value={[profile.city, profile.state].filter(Boolean).join(", ") || null}
                fallback="Not set"
              />
              <ProfileItem
                icon={<Calendar className="w-4 h-4 text-spf-navy" />}
                label="Available from"
                value={profile.available_from_date ?? profile.expected_completion_date ?? null}
                fallback="Not set"
              />
              <ProfileItem
                icon={<User className="w-4 h-4 text-spf-navy" />}
                label="Preferences"
                value={[
                  profile.willing_to_relocate ? "Open to relocate" : null,
                  profile.willing_to_travel ? "Open to travel" : null,
                ].filter(Boolean).join(" · ") || "Not specified"}
              />
            </div>

            {/* Alerts */}
            {(!profile.canonical_job_family_code ||
              (!profile.available_from_date && !profile.expected_completion_date) ||
              !profile.city) && (
              <div className="px-6 py-4 bg-amber-50/50 border-t border-amber-100 space-y-2">
                {!profile.canonical_job_family_code && (
                  <AlertRow>
                    Your program hasn&apos;t been matched to a job family.{" "}
                    <Link href="/applicant/profile" className="underline font-medium">Update profile</Link> to auto-match.
                  </AlertRow>
                )}
                {!profile.available_from_date && !profile.expected_completion_date && (
                  <AlertRow>
                    No availability date set.{" "}
                    <Link href="/applicant/profile" className="underline font-medium">Set your dates</Link> for better timing matches.
                  </AlertRow>
                )}
                {!profile.city && (
                  <AlertRow>
                    No city set.{" "}
                    <Link href="/applicant/profile" className="underline font-medium">Add your location</Link> for geography matching.
                  </AlertRow>
                )}
              </div>
            )}
          </section>
        )}

        {/* Matches */}
        {matches && (
          <section>
            <h2 className="font-semibold text-gray-900 mb-4 text-sm">Match summary</h2>

            {!matches.has_matches ? (
              <NoMatchesCard
                profileHasFamily={matches.profile_has_family}
                profileHasLocation={matches.profile_has_location}
              />
            ) : (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <StatCard
                    count={matches.total_eligible}
                    label="Eligible matches"
                    description="You meet the key requirements"
                    variant="eligible"
                    href="/applicant/matches"
                  />
                  <StatCard
                    count={matches.total_near_fit}
                    label="Near-fit matches"
                    description="Close — one or two addressable gaps"
                    variant="near_fit"
                    href="/applicant/matches#near-fit"
                  />
                </div>
                <div className="mt-4">
                  <Link
                    href="/applicant/matches"
                    className="inline-flex items-center gap-1.5 text-sm font-medium text-spf-navy hover:text-spf-navy-light transition-colors"
                  >
                    View all ranked jobs <ArrowRight className="w-4 h-4" />
                  </Link>
                </div>
              </>
            )}
          </section>
        )}
      </div>
    </main>
  );
}

function ProfileItem({
  icon,
  label,
  value,
  fallback = "—",
}: {
  icon: React.ReactNode;
  label: string;
  value: string | null | undefined;
  fallback?: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="mt-0.5 p-1.5 bg-gray-50 rounded-md">{icon}</div>
      <div className="min-w-0">
        <dt className="text-xs font-medium text-gray-400 uppercase tracking-wider">{label}</dt>
        <dd className={`mt-0.5 text-sm ${value ? "text-gray-900" : "text-gray-400 italic"}`}>
          {value ?? fallback}
        </dd>
      </div>
    </div>
  );
}

function CompletenessBar({ score }: { score: number }) {
  const color = score >= 80 ? "bg-green-500" : score >= 50 ? "bg-amber-500" : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs text-gray-500 tabular-nums">{score}%</span>
    </div>
  );
}

function AlertRow({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 text-xs text-amber-700">
      <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

function StatCard({
  count,
  label,
  description,
  variant,
  href,
}: {
  count: number;
  label: string;
  description: string;
  variant: "eligible" | "near_fit";
  href: string;
}) {
  const accent = variant === "eligible"
    ? "border-l-green-500 bg-green-50/30"
    : "border-l-spf-orange bg-orange-50/30";
  const countColor = variant === "eligible" ? "text-green-700" : "text-spf-orange";

  return (
    <Link
      href={href}
      className={`bg-white border border-gray-200 border-l-4 ${accent} rounded-xl p-5 hover:shadow-sm transition-shadow block group`}
    >
      <div className={`text-3xl font-bold ${countColor} tabular-nums`}>{count}</div>
      <div className="text-sm font-semibold text-gray-900 mt-1">{label}</div>
      <div className="text-xs text-gray-500 mt-0.5">{description}</div>
      <div className="mt-3 text-xs font-medium text-spf-navy group-hover:underline flex items-center gap-1">
        View details <ChevronRight className="w-3 h-3" />
      </div>
    </Link>
  );
}

function NoMatchesCard({
  profileHasFamily,
  profileHasLocation,
}: {
  profileHasFamily: boolean;
  profileHasLocation: boolean;
}) {
  const allReady = profileHasFamily && profileHasLocation;

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-6">
      <p className="text-gray-900 font-semibold">No matches yet</p>

      {allReady ? (
        <div className="mt-3">
          <p className="text-sm text-gray-600">
            Your profile is ready. Matches appear after the scoring pipeline runs.
          </p>
          <div className="flex items-center gap-2 mt-3 text-xs text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span className="font-medium">Profile ready for matching</span>
          </div>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <p className="text-sm text-gray-500">
            Complete your profile to enable matching:
          </p>
          <div className="space-y-2">
            <ChecklistItem done={profileHasFamily} label={profileHasFamily ? "Program matched to job family" : "Program not matched to job family"} />
            <ChecklistItem done={profileHasLocation} label={profileHasLocation ? "Location set" : "Location needed for geography matching"} />
          </div>
          {(!profileHasFamily || !profileHasLocation) && (
            <Link
              href="/applicant/profile"
              className="inline-flex items-center gap-1.5 mt-1 text-sm font-medium text-spf-navy hover:underline"
            >
              Complete your profile <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

function ChecklistItem({ done, label }: { done: boolean; label: string }) {
  return (
    <div className={`flex items-center gap-2 text-sm ${done ? "text-green-700" : "text-amber-700"}`}>
      {done ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
      <span>{label}</span>
    </div>
  );
}
