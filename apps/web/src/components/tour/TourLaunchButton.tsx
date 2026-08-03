"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { HelpCircle } from "lucide-react";

import { DASHBOARD_ROOTS, pageTourFor } from "@/lib/tours";
import { useTour } from "./TourProvider";

/**
 * The quiet grey tour icon that lives in the page header, top right.
 * Hidden when the page has no registered tour (and outside the dashboard,
 * where there is no TourProvider). On a role's dashboard root it offers both
 * the page tour and the full persona walkthrough.
 */
export function TourLaunchButton({ className = "" }: { className?: string }) {
  const ctx = useTour();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  // Close the menu on outside click or Esc.
  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  if (!ctx) return null;
  const pageTour = pageTourFor(pathname);
  const offerWalkthrough = DASHBOARD_ROOTS.has(pathname) && ctx.walkthroughId !== null;
  if (!pageTour && !offerWalkthrough) return null;

  const button = (
    <button
      type="button"
      aria-label="Tour this page"
      title="Tour this page"
      aria-haspopup={offerWalkthrough && pageTour ? "menu" : undefined}
      aria-expanded={offerWalkthrough && pageTour ? menuOpen : undefined}
      onClick={() => {
        if (offerWalkthrough && pageTour) {
          setMenuOpen((v) => !v);
        } else if (pageTour) {
          ctx.startTour(pageTour.id);
        } else if (ctx.walkthroughId) {
          ctx.startTour(ctx.walkthroughId);
        }
      }}
      className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-hairline bg-white text-slate-muted transition-colors hover:bg-stone/60 hover:text-cohere-ink focus-visible:outline-2 focus-visible:outline-studio-maroon focus-visible:outline-offset-2"
    >
      <HelpCircle className="h-[18px] w-[18px]" strokeWidth={1.75} aria-hidden="true" />
    </button>
  );

  if (!(offerWalkthrough && pageTour)) return <span className={className}>{button}</span>;

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      {button}
      {menuOpen && (
        <div
          role="menu"
          className="absolute right-0 top-full z-40 mt-1 w-48 overflow-hidden rounded-[10px] border border-hairline bg-white py-1 shadow-float"
        >
          <button
            role="menuitem"
            onClick={() => {
              setMenuOpen(false);
              ctx.startTour(pageTour.id);
            }}
            className="block w-full px-3 py-2 text-left text-caption text-cohere-ink transition-colors hover:bg-stone/50"
          >
            Tour this page
          </button>
          <button
            role="menuitem"
            onClick={() => {
              setMenuOpen(false);
              if (ctx.walkthroughId) ctx.startTour(ctx.walkthroughId);
            }}
            className="block w-full px-3 py-2 text-left text-caption text-cohere-ink transition-colors hover:bg-stone/50"
          >
            Take the full tour
          </button>
        </div>
      )}
    </div>
  );
}
