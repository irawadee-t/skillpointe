import { Suspense } from "react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowRight } from "lucide-react";

import { fetchMyBadges, fetchMyMatches, fetchMyProfile } from "@/lib/api/applicant";
import type { JobMatchSummary } from "@/lib/api/applicant";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { canViewApplicantPages } from "@/lib/viewAs.server";
import { formatDate } from "@/lib/format";
import { Reveal } from "@/components/ui";
import { RouteLoading } from "@/components/ui/RouteLoading";
import { TourWelcomeBand } from "@/components/tour/TourWelcomeBand";
import { TourLaunchButton } from "@/components/tour/TourLaunchButton";
import { ApiUnreachable } from "@/components/applicant/ApiUnreachable";
import { BadgeGrid } from "@/components/badges/BadgeGrid";

/**
 * Applicant dashboard — editorial, not dashboard-y.
 *
 * Design rules (the anti-"AI dashboard" contract):
 *  - Text on canvas, not boxes-in-boxes. One surface style: white, hairline.
 *  - The top match leads BY NAME — never a grid of counters.
 *  - Numbers live inside sentences ("2 ready to apply · 48 close"), never as
 *    a big numeral with a whisper label under it.
 *  - No gradient washes, no icon bubbles, no progress rings.
 */
export default async function ApplicantDashboard() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();

  if (!session) redirect("/login");
  if (!(await canViewApplicantPages(session.user.app_metadata?.role))) redirect("/login");

  // Stream: paint the route shell instantly while profile/matches/badges load.
  // Data fetching below is unchanged — only where it is awaited moved.
  return (
    <Suspense fallback={<RouteLoading variant="list" />}>
      <ApplicantHome
        token={session.access_token}
        isAdminViewAs={session.user.app_metadata?.role === "admin"}
      />
    </Suspense>
  );
}

async function ApplicantHome({
  token,
  isAdminViewAs,
}: {
  token: string;
  isAdminViewAs: boolean;
}) {
  let profileMissing = false;
  // Kick off all three fetches together — matches/badges don't depend on the
  // profile response, only on whether we redirect (in which case the extra
  // in-flight requests are simply discarded).
  const matchesPromise = fetchMyMatches(token).catch(() => null);
  const badgesPromise = fetchMyBadges(token).catch(() => null);
  const profile = await fetchMyProfile(token).catch((e) => {
    if (e instanceof ApiError && e.status === 404) { profileMissing = true; return null; }
    return null; // API unreachable — render error state below
  });

  // Under admin view-as, a missing profile must not bounce the admin into the
  // applicant onboarding wizard — surface the state instead.
  if (profileMissing) {
    if (isAdminViewAs) {
      return (
        <main className="py-10">
          <div className="page-shell">
            <h1 className="font-display text-heading text-cohere-ink leading-tight">
              No profile to view
            </h1>
            <p className="mt-2 max-w-xl text-body text-slate">
              This applicant has no linked profile yet. Pick another applicant
              from the debug bar above, or exit view-as.
            </p>
          </div>
        </main>
      );
    }
    redirect("/applicant/setup");
  }
  if (!profile) return <ApiUnreachable />;

  const [matches, badges] = await Promise.all([matchesPromise, badgesPromise]);

  const nextStep = deriveNextStep(profile);
  const completeness = profile?.profile_completeness ?? 0;
  const showFinishSetup = completeness < 50;
  const firstName = profile?.first_name?.trim() || null;

  const topMatches: JobMatchSummary[] = [
    ...(matches?.eligible_matches ?? []),
    ...(matches?.near_fit_matches ?? []),
  ].slice(0, 3);

  const totalMatches = (matches?.total_eligible ?? 0) + (matches?.total_near_fit ?? 0);

  return (
    <main className="py-10">
      <div className="page-shell">
        {completeness >= 50 && (
          <TourWelcomeBand displayName={profile ? `${profile.first_name ?? ""} ${profile.last_name ?? ""}`.trim() : null} />
        )}

        {/* Greeting — plain text on the canvas. No box, no ring. */}
        <Reveal as="section">
          <div className="flex items-start justify-between gap-4">
            <h1 className="font-display text-heading text-cohere-ink leading-tight">
              {greeting()}{firstName ? `, ${firstName}` : ""}.
            </h1>
            <TourLaunchButton className="mt-1" />
          </div>
          {matches?.has_matches ? (
            <p className="mt-2 max-w-xl text-body text-slate">
              {matches.total_eligible > 0 ? (
                <>You&rsquo;re ready to apply to <span className="font-medium text-cohere-ink">{matches.total_eligible} {matches.total_eligible === 1 ? "job" : "jobs"}</span>, and {matches.total_near_fit} more {matches.total_near_fit === 1 ? "is" : "are"} within reach.</>
              ) : (
                <>{totalMatches} jobs are close, a small gap or two away from ready.</>
              )}
            </p>
          ) : (
            <p className="mt-2 max-w-xl text-body text-slate">
              Your matches will appear here once your profile is ready.
            </p>
          )}
        </Reveal>

        {/* Finish setup — the one prominent call when the profile is thin. */}
        {showFinishSetup && (
          <Reveal as="section" className="mt-8 rounded-[10px] border border-hairline bg-white p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-[1.0625rem] font-medium text-cohere-ink leading-tight">
                  Finish setting up
                </p>
                <p className="mt-1 text-body text-slate">
                  About three minutes. Then your ranked matches start arriving.
                </p>
              </div>
              <Link href="/applicant/setup" className="btn-md shrink-0 self-start sm:self-auto">
                Start setup <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </Reveal>
        )}

        {/* Top matches — the actual jobs, by name. This is the page's point. */}
        {matches?.has_matches && topMatches.length > 0 && (
          <Reveal as="section" className="mt-10" delay={0.05} data-tour-id="dashboard-best-matches">
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="font-display text-feature text-cohere-ink">Your best matches</h2>
              <Link
                href="/applicant/matches"
                className="text-body text-slate transition-colors hover:text-cohere-ink"
              >
                All {totalMatches} <ArrowRight className="inline h-3.5 w-3.5" />
              </Link>
            </div>

            <div className="mt-4 overflow-hidden rounded-[10px] border border-hairline bg-white">
              {topMatches.map((m, i) => (
                <Link
                  key={m.match_id}
                  href={`/applicant/matches/${m.match_id}`}
                  className={`group flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-parchment/60 ${i > 0 ? "border-t border-hairline" : ""}`}
                >
                  <div className="min-w-0">
                    <p className="truncate text-body font-medium text-cohere-ink">
                      {m.job_title}
                    </p>
                    <p className="mt-0.5 truncate text-caption text-slate">
                      {m.employer_name}
                      {m.eligibility_status === "eligible"
                        ? " · Ready to apply"
                        : " · Close match"}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    {m.policy_adjusted_score !== null && (
                      <span className="text-body tabular-nums text-slate">
                        {Math.min(99, Math.floor(m.policy_adjusted_score))}
                      </span>
                    )}
                    <ArrowRight className="h-4 w-4 text-slate-muted transition-transform group-hover:translate-x-0.5" />
                  </div>
                </Link>
              ))}
            </div>
          </Reveal>
        )}

        {/* No matches yet — plain guidance, no card theater. */}
        {matches && !matches.has_matches && (
          <Reveal as="section" className="mt-10" delay={0.05}>
            <h2 className="font-display text-feature text-cohere-ink">No matches yet</h2>
            {matches.profile_has_family && matches.profile_has_location ? (
              <p className="mt-2 max-w-xl text-body text-slate">
                Your profile is ready. Matches appear after the next scoring run.
              </p>
            ) : (
              <p className="mt-2 max-w-xl text-body text-slate">
                {!matches.profile_has_family && "Add your program so we can match you to the right trade. "}
                {!matches.profile_has_location && "Add your city so we can find jobs within reach. "}
                <Link href="/applicant/profile" className="font-medium text-cohere-ink underline decoration-hairline underline-offset-4 hover:decoration-cohere-ink">
                  Complete your profile
                </Link>
                .
              </p>
            )}
          </Reveal>
        )}

        {/* Profile — a quiet fact sheet. Hairline rows, no icons, no dark panel. */}
        {profile && (
          <Reveal as="section" className="mt-10" delay={0.1}>
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="font-display text-feature text-cohere-ink">Profile</h2>
              <Link
                href="/applicant/profile"
                className="text-body text-slate transition-colors hover:text-cohere-ink"
              >
                Edit
              </Link>
            </div>

            <dl className="mt-4 overflow-hidden rounded-[10px] border border-hairline bg-white">
              <FactRow label="Program" value={profile.program_name_raw ?? null} first />
              <FactRow
                label="Location"
                value={[profile.city, profile.state].filter(Boolean).join(", ") || null}
              />
              {/* Human date via the shared formatter — "Sep 1, 2026", never raw ISO. */}
              <FactRow
                label="Available from"
                value={formatDate(profile.available_from_date ?? profile.expected_completion_date) || null}
              />
              <FactRow
                label="Preferences"
                value={[
                  profile.willing_to_relocate ? "Open to relocating" : null,
                  profile.willing_to_travel ? "Open to travel" : null,
                ].filter(Boolean).join(" · ") || null}
              />
            </dl>

            {/* Completeness + the single next step, as a sentence. */}
            {completeness < 100 && nextStep && (
              <p className="mt-3 text-caption text-slate">
                Your profile is {completeness}% complete.{" "}
                <Link href={nextStep.href} className="font-medium text-cohere-ink underline decoration-hairline underline-offset-4 hover:decoration-cohere-ink">
                  {nextStep.label}
                </Link>
                {nextStep.unlockHint ? `: ${nextStep.unlockHint.replace(/\.$/, "").toLowerCase()}.` : ""}
              </p>
            )}
          </Reveal>
        )}

        {/* Badges — earned from real activity, never decoration. This grid is
            the one surface where a subtle pointer tilt is sanctioned. */}
        {badges && badges.badges.length > 0 && (
          <Reveal as="section" className="mt-10" delay={0.15}>
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="font-display text-feature text-cohere-ink">Your badges</h2>
              <p className="text-body text-slate tabular-nums">
                {badges.earned_count} of {badges.total_count} earned
              </p>
            </div>
            <div className="mt-4">
              <BadgeGrid badges={badges.badges} />
            </div>
          </Reveal>
        )}
      </div>
    </main>
  );
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 5) return "Working late";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function FactRow({
  label,
  value,
  first = false,
}: {
  label: string;
  value: string | null;
  first?: boolean;
}) {
  return (
    <div className={`grid grid-cols-[8rem_1fr] gap-4 px-5 py-3.5 sm:grid-cols-[10rem_1fr] ${first ? "" : "border-t border-hairline"}`}>
      <dt className="text-body text-slate">{label}</dt>
      <dd className={`text-body ${value ? "text-cohere-ink" : "text-slate-muted"}`}>
        {value ?? "Not set"}
      </dd>
    </div>
  );
}

function deriveNextStep(profile: Awaited<ReturnType<typeof fetchMyProfile>>): { label: string; href: string; unlockHint?: string } | null {
  if (!profile) return { label: "Finish setting up your profile", href: "/applicant/setup" };
  if (!profile.state)             return { label: "Add your state",             href: "/applicant/profile", unlockHint: "Shows jobs near you." };
  if (!profile.city)              return { label: "Add your city",              href: "/applicant/profile", unlockHint: "Sharpens your matches by drive time." };
  // Trade is satisfied by EITHER a resolved trade family OR a typed program —
  // only nudge when both are missing, so a user who picked a trade in the
  // wizard isn't told to "add your trade" while their trade is shown.
  if (!profile.canonical_job_family_code && !profile.program_name_raw)
    return { label: "Add your trade or program", href: "/applicant/profile", unlockHint: "Anchors your matches to the right jobs." };
  if ((profile.profile_completeness ?? 0) < 80) return { label: "Fill in the rest", href: "/applicant/profile", unlockHint: "Completing your profile shows employers you're serious." };
  return { label: "See your matches", href: "/applicant/matches" };
}
