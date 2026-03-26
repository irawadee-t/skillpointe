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
      <div className="max-w-5xl mx-auto bg-rose-500/10 border border-rose-500/30 rounded-lg p-5 text-sm text-rose-400">
        <strong>Could not reach the API.</strong> The backend may be starting up — please refresh in a moment.
      </div>
    </main>
  );

  const matches = await fetchMyMatches(token).catch(() => null);

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold tracking-tight text-white">
            {profile?.first_name ? `Welcome back, ${profile.first_name}` : "Dashboard"}
          </h1>
          <Link
            href="/applicant/profile"
            className="text-sm font-medium text-zinc-400 hover:text-white transition-colors flex items-center gap-1"
          >
            Edit profile <ChevronRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Profile card */}
        {profile && (
          <section className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
              <h2 className="font-semibold text-white text-sm">Profile overview</h2>
              <CompletenessBar score={profile.profile_completeness} />
            </div>
            <div className="px-6 py-5 grid grid-cols-1 sm:grid-cols-2 gap-5">
              <ProfileItem
                icon={<Briefcase className="w-4 h-4 text-zinc-400" />}
                label="Program"
                value={profile.canonical_job_family_code
                  ? `${profile.program_name_raw ?? ""} (${profile.canonical_job_family_code})`
                  : (profile.program_name_raw ?? null)}
                fallback="Not set"
              />
              <ProfileItem
                icon={<MapPin className="w-4 h-4 text-zinc-400" />}
                label="Location"
                value={[profile.city, profile.state].filter(Boolean).join(", ") || null}
                fallback="Not set"
              />
              <ProfileItem
                icon={<Calendar className="w-4 h-4 text-zinc-400" />}
                label="Available from"
                value={profile.available_from_date ?? profile.expected_completion_date ?? null}
                fallback="Not set"
              />
              <ProfileItem
                icon={<User className="w-4 h-4 text-zinc-400" />}
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
              <div className="px-6 py-4 bg-zinc-800/50 border-t border-zinc-800 space-y-2">
                {!profile.canonical_job_family_code && (
                  <AlertRow>
                    Your program hasn&apos;t been matched to a job family.{" "}
                    <Link href="/applicant/profile" className="underline font-medium text-cyan-400">Update profile</Link> to auto-match.
                  </AlertRow>
                )}
                {!profile.available_from_date && !profile.expected_completion_date && (
                  <AlertRow>
                    No availability date set.{" "}
                    <Link href="/applicant/profile" className="underline font-medium text-cyan-400">Set your dates</Link> for better timing matches.
                  </AlertRow>
                )}
                {!profile.city && (
                  <AlertRow>
                    No city set.{" "}
                    <Link href="/applicant/profile" className="underline font-medium text-cyan-400">Add your location</Link> for geography matching.
                  </AlertRow>
                )}
              </div>
            )}
          </section>
        )}

        {/* Matches */}
        {matches && (
          <section>
            <h2 className="font-semibold text-white mb-4 text-sm">Match summary</h2>

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
                    className="inline-flex items-center gap-1.5 text-sm font-medium text-cyan-400 hover:text-cyan-300 transition-colors"
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
      <div className="mt-0.5 p-1.5 bg-zinc-800 rounded-md">{icon}</div>
      <div className="min-w-0">
        <dt className="text-xs font-medium text-zinc-500 uppercase tracking-widest">{label}</dt>
        <dd className={`mt-0.5 text-sm ${value ? "text-white" : "text-zinc-500 italic"}`}>
          {value ?? fallback}
        </dd>
      </div>
    </div>
  );
}

function CompletenessBar({ score }: { score: number }) {
  const color = score >= 80 ? "bg-gradient-to-r from-cyan-500 to-blue-600" : score >= 50 ? "bg-amber-500" : "bg-zinc-600";
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all duration-700`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs text-zinc-400 tabular-nums">{score}%</span>
    </div>
  );
}

function AlertRow({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 text-xs text-zinc-500">
      <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-400" />
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
    ? "border-l-emerald-500"
    : "border-l-amber-500";

  return (
    <Link
      href={href}
      className={`bg-zinc-900 border border-zinc-800 border-l-4 ${accent} rounded-lg p-5 hover:border-zinc-700 transition-colors block group`}
    >
      <div className={`text-3xl font-bold tabular-nums ${variant === "eligible" ? "text-emerald-400" : "text-amber-400"}`}>{count}</div>
      <div className="text-sm font-semibold text-white mt-1">{label}</div>
      <div className="text-xs text-zinc-500 mt-0.5">{description}</div>
      <div className="mt-3 text-xs font-medium text-zinc-500 group-hover:text-cyan-400 flex items-center gap-1 transition-colors">
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
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
      <p className="text-white font-semibold">No matches yet</p>

      {allReady ? (
        <div className="mt-3">
          <p className="text-sm text-zinc-400">
            Your profile is ready. Matches appear after the scoring pipeline runs.
          </p>
          <div className="flex items-center gap-2 mt-3 text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span className="font-medium">Profile ready for matching</span>
          </div>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <p className="text-sm text-zinc-500">
            Complete your profile to enable matching:
          </p>
          <div className="space-y-2">
            <ChecklistItem done={profileHasFamily} label={profileHasFamily ? "Program matched to job family" : "Program not matched to job family"} />
            <ChecklistItem done={profileHasLocation} label={profileHasLocation ? "Location set" : "Location needed for geography matching"} />
          </div>
          {(!profileHasFamily || !profileHasLocation) && (
            <Link
              href="/applicant/profile"
              className="inline-flex items-center gap-1.5 mt-1 text-sm font-medium text-cyan-400 hover:text-cyan-300"
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
    <div className={`flex items-center gap-2 text-sm ${done ? "text-emerald-400" : "text-zinc-500"}`}>
      {done ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4 text-amber-400" />}
      <span>{label}</span>
    </div>
  );
}
