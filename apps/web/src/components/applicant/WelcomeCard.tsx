"use client";

import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";

import { MonoLabel } from "@/components/ui";
import { timeOfDayGreeting } from "@/lib/time";

/**
 * Applicant dashboard hero — time-of-day greeting + profile-completeness ring
 * with a specific next step. Replaces the generic "Dashboard" heading.
 *
 * Design: reuses the site's rounded-xl card language and coral eyebrow;
 * the ring uses the existing green/coral/blue palette (no new colors).
 */
export function WelcomeCard({
  displayName, completeness, nextStep, matchCount, applicationCount, viewedRecently, onboardingComplete,
}: {
  displayName?: string | null;
  completeness: number;       // 0..100
  nextStep?: { label: string; href: string; unlockHint?: string } | null;
  matchCount?: number;
  applicationCount?: number;
  viewedRecently?: number;    // employer views in last 7 days
  onboardingComplete?: boolean;
}) {
  // Pick a state — greeting stays the same, subhead + primary CTA vary.
  // Falls through the states top-to-bottom so the earliest matching one wins.
  const state = pickState({ completeness, matchCount, onboardingComplete });

  const subhead = STATE_COPY[state].subhead(nextStep, matchCount, viewedRecently);
  const cta = STATE_COPY[state].cta(nextStep);

  return (
    <section className="aurora-surface rounded-xl p-6 sm:p-7">
      <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <MonoLabel className="text-studio-cream/60">{new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}</MonoLabel>
          <h1 className="mt-2 font-display text-heading text-studio-cream">
            {timeOfDayGreeting(displayName)}
          </h1>
          <p className="mt-2 max-w-prose text-body-lg text-studio-cream/80">
            {subhead}
          </p>

          {(matchCount != null || applicationCount != null) && (
            <div className="mt-5 flex flex-wrap gap-6">
              {matchCount != null && <Stat label="Matches this week" value={matchCount} />}
              {applicationCount != null && <Stat label="Open applications" value={applicationCount} />}
              {viewedRecently != null && viewedRecently > 0 && <Stat label="Employer views" value={viewedRecently} />}
            </div>
          )}

          {cta && (
            <Link href={cta.href}
              className="mt-6 inline-flex items-center gap-1.5 text-body font-medium text-studio-cream underline decoration-studio-sienna decoration-2 underline-offset-4 hover:decoration-studio-cream"
            >
              <Sparkles className="h-4 w-4 text-studio-sienna" strokeWidth={2} />
              {cta.label}
              <ArrowRight className="h-4 w-4" />
            </Link>
          )}
        </div>

        <div className="flex shrink-0 justify-center sm:justify-end">
          <ProgressRing pct={completeness} unlockHint={nextStep?.unlockHint} />
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------
type WelcomeState = "unstarted" | "in_progress" | "ready_awaiting" | "steady";

function pickState({
  completeness, matchCount, onboardingComplete,
}: {
  completeness: number;
  matchCount?: number;
  onboardingComplete?: boolean;
}): WelcomeState {
  // Treat completeness < 40 as unstarted regardless of onboarding_complete —
  // some accounts skip through the wizard without answering the key fields.
  if (onboardingComplete === false || completeness < 40) return "unstarted";
  if (completeness < 80) return "in_progress";
  if ((matchCount ?? 0) === 0) return "ready_awaiting";
  return "steady";
}

const STATE_COPY: Record<WelcomeState, {
  subhead: (
    nextStep?: { label: string; href: string; unlockHint?: string } | null,
    matchCount?: number,
    viewedRecently?: number,
  ) => string;
  cta: (
    nextStep?: { label: string; href: string; unlockHint?: string } | null,
  ) => { label: string; href: string } | null;
}> = {
  unstarted: {
    subhead: () => "Let's finish setting up. Two more minutes and jobs start ranking for you.",
    cta:      () => ({ label: "Continue setup", href: "/applicant/setup" }),
  },
  in_progress: {
    subhead: (nextStep) =>
      nextStep
        ? `Almost there — add ${nextStep.label.toLowerCase()} to bring in more matches.`
        : "Almost there — a few more details will bring in more matches.",
    cta: (nextStep) => nextStep ? { label: nextStep.label, href: nextStep.href } : null,
  },
  ready_awaiting: {
    subhead: () => "Your profile is ready. Matches will appear within the next hour.",
    cta:      () => null,
  },
  steady: {
    subhead: (nextStep, _mc, viewedRecently) =>
      viewedRecently && viewedRecently > 0
        ? `${viewedRecently} employer${viewedRecently === 1 ? " has" : "s have"} looked at your profile this week.`
        : "The more your profile has, the better we can match. A few missing pieces are keeping some jobs out of view.",
    cta: (nextStep) => nextStep ? { label: nextStep.label, href: nextStep.href } : null,
  },
};

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="font-display text-card text-studio-cream tabular-nums">{value}</span>
        <span className="text-caption font-medium text-studio-cream/60">{/^[A-Z][a-z]/.test(label) ? label.charAt(0).toLowerCase() + label.slice(1) : label}</span>
      </div>
    </div>
  );
}

/**
 * SVG progress ring — 96×96, 8px stroke, coral track, green fill.
 * Center shows percent and an optional line under it ("+ 8 more matches").
 */
function ProgressRing({ pct, unlockHint }: { pct: number; unlockHint?: string }) {
  const clamped = Math.max(0, Math.min(100, pct));
  const size = 128;
  const strokeW = 10;
  const r = (size - strokeW) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const c = 2 * Math.PI * r;
  const dash = (clamped / 100) * c;

  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="rotate-[-90deg]">
          <circle cx={cx} cy={cy} r={r} stroke="currentColor" strokeWidth={strokeW}
            className="text-white/15" fill="none" />
          <circle cx={cx} cy={cy} r={r} stroke="currentColor" strokeWidth={strokeW}
            className={clamped >= 100 ? "text-studio-cream" : "text-studio-sienna"} fill="none"
            strokeDasharray={`${dash} ${c}`} strokeLinecap="round" />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="font-display text-feature text-studio-cream tabular-nums">{clamped}%</div>
          <div className="mono-label text-studio-cream/55">Profile</div>
        </div>
      </div>
      {unlockHint && (
        <p className="mt-3 max-w-[180px] text-center text-caption text-studio-cream/60">{unlockHint}</p>
      )}
    </div>
  );
}
