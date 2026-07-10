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
import { PageHeader, MonoLabel, MetricCard, Reveal, Stagger, StaggerItem } from "@/components/ui";
import { WelcomeCard } from "@/components/applicant/WelcomeCard";
import { CoachMarkTour } from "@/components/applicant/CoachMarkTour";
import { ApiUnreachable } from "@/components/applicant/ApiUnreachable";

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
  if (!profile) return <ApiUnreachable />;

  const matches = await fetchMyMatches(token).catch(() => null);

  const nextStep = deriveNextStep(profile);
  const completeness = profile?.profile_completeness ?? 0;
  const showFinishSetup = completeness < 50;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <CoachMarkTour displayName={profile ? `${profile.first_name ?? ""} ${profile.last_name ?? ""}`.trim() : null} />

        {/* Finish setup banner — auto-hides at completeness >= 50 */}
        {showFinishSetup && (
          <Reveal
            as="section"
            className="rounded-md border border-hairline bg-parchment p-6"
          >
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <div className="min-w-0">
                  <p className="font-display text-feature text-cohere-ink leading-tight">
                    Finish setting up
                  </p>
                  <p className="mt-1 text-body text-slate">
                    About three minutes. Then your ranked matches start arriving.
                  </p>
                </div>
              </div>
              <Link href="/applicant/setup" className="btn-lg shrink-0 self-start sm:self-auto">
                Start setup <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </Reveal>
        )}

        <WelcomeCard
          displayName={profile ? `${profile.first_name ?? ""} ${profile.last_name ?? ""}`.trim() : null}
          completeness={profile?.profile_completeness ?? 0}
          nextStep={nextStep}
          matchCount={(matches?.eligible_matches?.length ?? 0) + (matches?.near_fit_matches?.length ?? 0)}
          applicationCount={undefined}
          viewedRecently={undefined}
        />

        {/* Profile card — deep-green hero panel */}
        {profile && (
          <Reveal as="section" className="card-green overflow-hidden">
            <div className="px-6 py-4 border-b border-white/15 flex items-center justify-between">
              <MonoLabel className="text-white/70">Profile overview</MonoLabel>{/* Item 14: standardized on "Profile overview" */}
              <CompletenessBar score={profile.profile_completeness} />
            </div>
            <div className="px-6 py-5 grid grid-cols-1 sm:grid-cols-2 gap-5">
              <ProfileItem
                icon={<Briefcase className="w-4 h-4 text-white/80" />}
                label="Program"
                value={profile.canonical_job_family_code
                  ? `${profile.program_name_raw ?? ""} (${profile.canonical_job_family_code})`
                  : (profile.program_name_raw ?? null)}
                fallback="Not set"
              />
              <ProfileItem
                icon={<MapPin className="w-4 h-4 text-white/80" />}
                label="Location"
                value={[profile.city, profile.state].filter(Boolean).join(", ") || null}
                fallback="Not set"
              />
              <ProfileItem
                icon={<Calendar className="w-4 h-4 text-white/80" />}
                label="Available from"
                value={profile.available_from_date ?? profile.expected_completion_date ?? null}
                fallback="Not set"
              />
              <ProfileItem
                icon={<User className="w-4 h-4 text-white/80" />}
                label="Preferences"
                value={[
                  profile.willing_to_relocate ? "Open to relocate" : null,
                  profile.willing_to_travel ? "Open to travel" : null,
                ].filter(Boolean).join(", ") || "Not specified"}
              />
            </div>

            {/* Alerts */}
            {(!profile.canonical_job_family_code ||
              (!profile.available_from_date && !profile.expected_completion_date) ||
              !profile.city) && (
              <div className="px-6 py-4 bg-white/5 border-t border-white/15 space-y-2">
                {!profile.canonical_job_family_code && (
                  <AlertRow>
                    Add your program info and roughly 20 more matches open up.{" "}
                    <Link href="/applicant/profile" className="underline font-medium text-white">Update profile</Link>.
                  </AlertRow>
                )}
                {!profile.available_from_date && !profile.expected_completion_date && (
                  <AlertRow>
                    Add your availability date so employers know when you can start — near-fit matches drop without it.{" "}
                    <Link href="/applicant/profile" className="underline font-medium text-white">Set your dates</Link>.
                  </AlertRow>
                )}
                {!profile.city && (
                  <AlertRow>
                    Add your city to see jobs within commute range — right now you&apos;re missing local matches.{" "}
                    <Link href="/applicant/profile" className="underline font-medium text-white">Add your location</Link>.
                  </AlertRow>
                )}
              </div>
            )}
          </Reveal>
        )}

        {/* Matches */}
        {matches && (
          <Reveal as="section" delay={0.05}>
            <MonoLabel className="mb-4 block">Match summary</MonoLabel>

            {!matches.has_matches ? (
              <NoMatchesCard
                profileHasFamily={matches.profile_has_family}
                profileHasLocation={matches.profile_has_location}
              />
            ) : (
              <>
                <Stagger className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <StaggerItem>
                    <StatCard
                      count={matches.total_eligible}
                      label="Eligible matches"
                      description="You meet the key requirements"
                      variant="eligible"
                      href="/applicant/matches"
                    />
                  </StaggerItem>
                  <StaggerItem>
                    <StatCard
                      count={matches.total_near_fit}
                      label="Near-fit matches"
                      description="Close — one or two addressable gaps"
                      variant="near_fit"
                      href="/applicant/matches#near-fit"
                    />
                  </StaggerItem>
                </Stagger>
                <div className="mt-4">
                  <Link
                    href="/applicant/matches"
                    className="inline-flex items-center gap-1.5 text-body font-medium text-cohere-green hover:text-cohere-ink transition-colors"
                  >
                    View all ranked jobs <ArrowRight className="w-4 h-4" />
                  </Link>
                </div>
              </>
            )}
          </Reveal>
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
      <div className="mt-0.5 p-1.5 bg-white/10 rounded-sm">{icon}</div>
      <div className="min-w-0">
        <dt className="text-caption font-medium text-white/65">{label}</dt>
        <dd className={`mt-0.5 text-body ${value ? "text-white" : "text-white/50 italic"}`}>
          {value ?? fallback}
        </dd>
      </div>
    </div>
  );
}

function deriveNextStep(profile: Awaited<ReturnType<typeof fetchMyProfile>>): { label: string; href: string; unlockHint?: string } | null {
  if (!profile) return { label: "Finish setting up your profile", href: "/applicant/setup" };
  if (!profile.state)             return { label: "Add your state",             href: "/applicant/profile", unlockHint: "Unlocks jobs near you." };
  if (!profile.city)              return { label: "Add your city",              href: "/applicant/profile", unlockHint: "Sharpens your matches by drive time." };
  if (!profile.program_name_raw)  return { label: "Add your trade or program",  href: "/applicant/profile", unlockHint: "Anchors your matches to the right jobs." };
  if (!profile.canonical_job_family_code) return { label: "Confirm your trade family", href: "/applicant/profile", unlockHint: "Improves match quality." };
  if ((profile.profile_completeness ?? 0) < 80) return { label: "Fill in the rest of your profile", href: "/applicant/profile", unlockHint: "Completing your profile shows employers you're serious." };
  return { label: "See your matches", href: "/applicant/matches" };
}

function CompletenessBar({ score }: { score: number }) {
  const color = score >= 80 ? "bg-white" : score >= 50 ? "bg-cohere-coral" : "bg-white/30";
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-1.5 bg-white/15 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all duration-700`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-caption text-white tabular-nums">{score}%</span>
    </div>
  );
}

function AlertRow({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-2 text-caption text-white/80">
      <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-cohere-coral" />
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
  return (
    <Link href={href} className="block group h-full">
      <MetricCard
        label={label}
        value={count}
        sub={description}
        tone={variant === "eligible" ? "green" : "stone"}
        className="h-full"
      />
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
    <div className="bg-stone border border-transparent rounded-md p-6">
      <p className="font-display text-feature text-cohere-ink">No matches yet</p>

      {allReady ? (
        <div className="mt-3">
          <p className="text-body text-slate">
            Your profile is ready. Matches appear after the scoring pipeline runs.
          </p>
          <div className="flex items-center gap-2 mt-3 text-caption text-cohere-green bg-wash-green border border-cohere-green/20 rounded-sm px-3 py-2">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span className="font-medium">Profile ready for matching</span>
          </div>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <p className="text-body text-slate">
            Finish your profile to see jobs you&apos;re ready to apply to.
          </p>
          <div className="space-y-2">
            <ChecklistItem done={profileHasFamily} label={profileHasFamily ? "Program matched to job family" : "Program not matched to job family"} />
            <ChecklistItem done={profileHasLocation} label={profileHasLocation ? "Location set" : "Location needed for geography matching"} />
          </div>
          {(!profileHasFamily || !profileHasLocation) && (
            <Link
              href="/applicant/profile"
              className="inline-flex items-center gap-1.5 mt-1 text-body font-medium text-cohere-green hover:text-cohere-ink transition-colors"
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
    <div className={`flex items-center gap-2 text-body ${done ? "text-cohere-green" : "text-slate"}`}>
      {done ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4 text-cohere-coral" />}
      <span>{label}</span>
    </div>
  );
}
