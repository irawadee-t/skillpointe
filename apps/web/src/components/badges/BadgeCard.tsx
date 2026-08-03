"use client";

import {
  Award,
  Bookmark,
  Briefcase,
  Files,
  MessageSquare,
  MessagesSquare,
  Send,
  ShieldCheck,
  Sparkles,
  UserCheck,
  type LucideIcon,
} from "lucide-react";

import type { ApplicantBadge } from "@/lib/api/applicant";
import { TiltCard } from "./TiltCard";

const ICONS: Record<string, LucideIcon> = {
  profile_complete: UserCheck,
  first_credential: Award,
  five_credentials: Files,
  credential_verified: ShieldCheck,
  ten_jobs_saved: Bookmark,
  first_application: Send,
  ten_applications: Files,
  planning_chat: MessageSquare,
  first_employer_message: MessagesSquare,
  hired: Briefcase,
};

function earnedDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function BadgeCard({ badge }: { badge: ApplicantBadge }) {
  const Icon = ICONS[badge.key] ?? Sparkles;
  const { current, target } = badge.progress;
  const pct = target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 0;
  const date = earnedDate(badge.earned_at);

  const card = (
    <div className="flex h-full flex-col rounded-[14px] border border-hairline bg-white p-6 transition-[box-shadow,border-color] duration-200 hover:shadow-float">
      <Icon
        aria-hidden
        strokeWidth={1.5}
        className={`h-8 w-8 ${badge.earned ? "text-studio-maroon" : "text-slate-muted opacity-60"}`}
      />
      <p
        className={`mt-4 text-[1rem] font-semibold leading-snug ${
          badge.earned ? "text-cohere-ink" : "text-slate"
        }`}
      >
        {badge.title}
      </p>
      <p className="mt-1 text-label text-slate">{badge.description}</p>

      <div className="mt-auto pt-4">
        {badge.earned ? (
          <p className="text-caption text-slate-muted">
            {date ? `Earned ${date}` : "Earned"}
          </p>
        ) : (
          <>
            <div
              className="h-1.5 w-full overflow-hidden rounded-full bg-hairline"
              role="progressbar"
              aria-valuenow={current}
              aria-valuemin={0}
              aria-valuemax={target}
              aria-label={`${badge.title} progress`}
            >
              <div
                className="h-full rounded-full bg-cohere-ink transition-[width] duration-200"
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="mt-2 text-caption tabular-nums text-slate-muted">
              {badge.key === "profile_complete"
                ? `${current}% of ${target}% complete`
                : `${current} of ${target}`}
            </p>
          </>
        )}
      </div>
    </div>
  );

  // The one sanctioned delight moment — earned badges only, pointer-only,
  // off under reduced motion. See DESIGN_CONTRACT.md.
  return badge.earned ? <TiltCard className="h-full">{card}</TiltCard> : card;
}
