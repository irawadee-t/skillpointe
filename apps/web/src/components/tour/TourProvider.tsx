"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { usePathname, useRouter } from "next/navigation";

import { getTour, pageTourFor, walkthroughFor, type Tour } from "@/lib/tours";
import {
  hasSeenTour,
  markTourSeen,
  readProgress,
  writeProgress,
} from "./storage";
import { TourOverlay } from "./TourOverlay";

/**
 * One tour system for the whole product.
 *
 * - Page tours run in place.
 * - Walkthroughs cross pages: between steps on different routes the provider
 *   persists progress, navigates, and resumes when the new page mounts. The
 *   same persistence makes a mid-tour reload resume instead of vanish.
 * - Nothing here ever traps: Esc and the card's exit always work, a quiet
 *   "Exit tour" pill shows while a walkthrough is in flight, and a pending
 *   resume is offered, never forced.
 */

export const START_TOUR_EVENT = "sn:start-tour";

type TourContextValue = {
  userId: string;
  role: string;
  activeTourId: string | null;
  startTour: (tourId: string) => void;
  exitTour: () => void;
  hasSeen: (tourId: string) => boolean;
  /** The walkthrough tour id for this role, if one exists. */
  walkthroughId: string | null;
};

const TourContext = createContext<TourContextValue | null>(null);

export function useTour(): TourContextValue | null {
  return useContext(TourContext);
}

type ActiveState = { tour: Tour; stepIx: number };

export function TourProvider({
  userId,
  role,
  children,
}: {
  userId: string;
  role: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();

  const [active, setActive] = useState<ActiveState | null>(null);
  // A walkthrough step on another route: navigation is in flight.
  const [navTarget, setNavTarget] = useState<ActiveState | null>(null);
  // Stored progress found on mount for a route we are not on.
  const [pendingResume, setPendingResume] = useState<ActiveState | null>(null);
  // Bump to re-read seen flags after completion.
  const [, setSeenTick] = useState(0);

  const walkthrough = useMemo(() => walkthroughFor(role), [role]);

  const finish = useCallback(
    (tour: Tour) => {
      markTourSeen(userId, tour.id);
      writeProgress(userId, null);
      setActive(null);
      setNavTarget(null);
      setPendingResume(null);
      setSeenTick((t) => t + 1);
    },
    [userId],
  );

  const goToStep = useCallback(
    (tour: Tour, stepIx: number) => {
      if (stepIx < 0) return;
      if (stepIx >= tour.steps.length) {
        finish(tour);
        return;
      }
      const step = tour.steps[stepIx];
      if (tour.kind === "walkthrough") {
        writeProgress(userId, { tourId: tour.id, stepIx });
      }
      if (step.route && step.route !== pathname) {
        setActive(null);
        setNavTarget({ tour, stepIx });
        router.push(step.route);
        return;
      }
      setNavTarget(null);
      setActive({ tour, stepIx });
    },
    [finish, pathname, router, userId],
  );

  const startTour = useCallback(
    (tourId: string) => {
      const tour = getTour(tourId);
      if (!tour) return;
      setPendingResume(null);
      goToStep(tour, 0);
    },
    [goToStep],
  );

  const exitTour = useCallback(() => {
    const tour = active?.tour ?? navTarget?.tour;
    if (tour) finish(tour);
  }, [active, navTarget, finish]);

  // Resume after a cross-page navigation lands.
  useEffect(() => {
    if (!navTarget) return;
    const step = navTarget.tour.steps[navTarget.stepIx];
    if (!step?.route || step.route === pathname) {
      setNavTarget(null);
      setActive(navTarget);
    }
  }, [navTarget, pathname]);

  // On mount: pick up stored walkthrough progress (reload-safe resume).
  useEffect(() => {
    const progress = readProgress(userId);
    if (!progress) return;
    const tour = getTour(progress.tourId);
    if (!tour || progress.stepIx >= tour.steps.length) {
      writeProgress(userId, null);
      return;
    }
    const step = tour.steps[progress.stepIx];
    if (!step.route || step.route === pathname) {
      setActive({ tour, stepIx: progress.stepIx });
    } else {
      setPendingResume({ tour, stepIx: progress.stepIx });
    }
    // Run once per provider mount only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  // If the user wanders onto the pending route on their own, resume there.
  useEffect(() => {
    if (!pendingResume || active || navTarget) return;
    const step = pendingResume.tour.steps[pendingResume.stepIx];
    if (step?.route === pathname) {
      setActive(pendingResume);
      setPendingResume(null);
    }
  }, [pathname, pendingResume, active, navTarget]);

  // Global launcher: sidebar "Take the tour", welcome bands, command palette.
  useEffect(() => {
    const onStart = (e: Event) => {
      const detail = (e as CustomEvent<{ tourId?: string }>).detail;
      const id = detail?.tourId ?? walkthrough?.id;
      if (id) startTour(id);
    };
    window.addEventListener(START_TOUR_EVENT, onStart);
    return () => window.removeEventListener(START_TOUR_EVENT, onStart);
  }, [startTour, walkthrough]);

  const value = useMemo<TourContextValue>(
    () => ({
      userId,
      role,
      activeTourId: active?.tour.id ?? navTarget?.tour.id ?? null,
      startTour,
      exitTour,
      hasSeen: (tourId: string) => hasSeenTour(userId, tourId),
      walkthroughId: walkthrough?.id ?? null,
    }),
    [userId, role, active, navTarget, startTour, exitTour, walkthrough],
  );

  const walkthroughInFlight =
    (active?.tour.kind === "walkthrough" || navTarget !== null) && !pendingResume;

  return (
    <TourContext.Provider value={value}>
      {children}

      {active && (
        <TourOverlay
          tour={active.tour}
          stepIx={active.stepIx}
          onNext={() => goToStep(active.tour, active.stepIx + 1)}
          onBack={() => goToStep(active.tour, active.stepIx - 1)}
          onExit={exitTour}
          onSkipMissing={() => goToStep(active.tour, active.stepIx + 1)}
        />
      )}

      {/* Quiet, persistent exit while a walkthrough is running or navigating. */}
      {walkthroughInFlight && (
        <button
          onClick={exitTour}
          className="fixed bottom-4 left-4 z-[76] rounded-full border border-hairline bg-white px-3 py-1.5 text-caption text-slate shadow-float transition-colors hover:text-cohere-ink"
        >
          Exit tour
        </button>
      )}

      {/* Interrupted walkthrough found in storage — offer, never force. */}
      {pendingResume && !active && !navTarget && (
        <div className="fixed bottom-4 left-4 z-[76] flex items-center gap-3 rounded-xl border border-hairline bg-white px-4 py-3 shadow-float">
          <p className="text-caption text-slate">
            You left a tour partway through.
          </p>
          <button
            onClick={() => {
              const r = pendingResume;
              setPendingResume(null);
              goToStep(r.tour, r.stepIx);
            }}
            className="text-caption font-medium text-cohere-ink underline decoration-hairline underline-offset-4 hover:decoration-cohere-ink"
          >
            Resume
          </button>
          <button
            onClick={() => finish(pendingResume.tour)}
            className="text-caption text-slate-muted transition-colors hover:text-cohere-ink"
          >
            Dismiss
          </button>
        </div>
      )}
    </TourContext.Provider>
  );
}

/** True when the current pathname has a registered page tour. */
export function usePageTour(pathname: string): Tour | null {
  return useMemo(() => pageTourFor(pathname), [pathname]);
}
