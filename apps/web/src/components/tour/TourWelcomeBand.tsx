"use client";

import { useEffect, useState } from "react";
import { ArrowRight, X } from "lucide-react";

import { useTour } from "./TourProvider";
import { dismissOffer, isOfferDismissed } from "./storage";

const COPY: Record<string, { lead: string; sub: string }> = {
  applicant: {
    lead: "Want a quick look around?",
    sub: "A two minute tour: matches, applications, credentials, and where to get help.",
  },
  employer: {
    lead: "Want a quick look around?",
    sub: "A two minute tour: posting jobs, the applications inbox, verified workers, and analytics.",
  },
  admin: {
    lead: "Want a quick look around?",
    sub: "A two minute tour: the queues, matching controls, and marketplace health.",
  },
};

/**
 * First-run welcome band — an inline, dismissible offer to take the persona
 * walkthrough. Never auto-starts anything and never blocks the page. Once the
 * walkthrough is finished or the band dismissed it stays gone for this user;
 * the header tour icon remains for re-runs.
 */
export function TourWelcomeBand({ displayName }: { displayName?: string | null }) {
  const ctx = useTour();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!ctx || !ctx.walkthroughId) return;
    if (ctx.hasSeen(ctx.walkthroughId)) return;
    if (isOfferDismissed(ctx.userId, ctx.role)) return;
    setVisible(true);
  }, [ctx]);

  if (!ctx || !ctx.walkthroughId || !visible || ctx.activeTourId) return null;

  const copy = COPY[ctx.role] ?? COPY.applicant;
  const first = displayName?.trim() ? displayName.trim().split(" ")[0] : null;

  const hide = () => {
    dismissOffer(ctx.userId, ctx.role);
    setVisible(false);
  };

  return (
    <section
      aria-label="Welcome"
      className="mb-8 rounded-[10px] border border-hairline bg-white px-5 py-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <p className="text-[1.0625rem] font-medium text-cohere-ink">
            Welcome{first ? `, ${first}` : ""}. {copy.lead}
          </p>
          <p className="mt-0.5 text-caption text-slate">{copy.sub}</p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <button
            onClick={() => {
              setVisible(false);
              if (ctx.walkthroughId) ctx.startTour(ctx.walkthroughId);
            }}
            className="btn-primary inline-flex items-center gap-1.5"
          >
            Show me around <ArrowRight className="h-4 w-4" />
          </button>
          <button
            onClick={hide}
            aria-label="Dismiss welcome"
            className="rounded-md p-1.5 text-slate-muted transition-colors hover:bg-stone/60 hover:text-cohere-ink"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    </section>
  );
}
