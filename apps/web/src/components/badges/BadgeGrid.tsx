import type { ApplicantBadge } from "@/lib/api/applicant";
import { BadgeCard } from "./BadgeCard";

/**
 * Badge showcase grid — earned badges first, then the ones still in progress
 * so the section reads as "what you've done" followed by "what's next".
 */
export function BadgeGrid({ badges }: { badges: ApplicantBadge[] }) {
  const ordered = [...badges].sort((a, b) => {
    if (a.earned !== b.earned) return a.earned ? -1 : 1;
    if (a.earned) {
      // Most recent achievement first.
      return (b.earned_at ?? "").localeCompare(a.earned_at ?? "");
    }
    // Closest to the finish line first.
    const ratio = (x: ApplicantBadge) =>
      x.progress.target > 0 ? x.progress.current / x.progress.target : 0;
    return ratio(b) - ratio(a);
  });

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {ordered.map((b) => (
        <BadgeCard key={b.key} badge={b} />
      ))}
    </div>
  );
}
