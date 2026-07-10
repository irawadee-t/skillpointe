"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowRight, X } from "lucide-react";
import { MonoLabel } from "@/components/ui";

const KEY = "skillpointe:coachmark-tour:v1";

/**
 * Coach-mark tour anchored to real UI elements. Renders on first login only.
 *
 * How it works:
 *   - Each step targets a real element by CSS selector.
 *   - A dim scrim covers the page; a "cutout" is drawn where the anchor is
 *     using a large box-shadow, so the anchor visually pops through.
 *   - A small tooltip card is positioned next to the anchor, edge-avoiding.
 *
 * Zero external deps. Dismisses to localStorage, never returns.
 */
type Step = {
  selector: string;               // element to spotlight
  title: string;
  body: string;
  placement?: "right" | "bottom" | "top";
};

const STEPS: Step[] = [
  {
    selector: 'a[href="/applicant/matches"]',
    title: "Where your matches live",
    body: "Real jobs, ranked. Each one tells you the score and the reason for it. Open one to see the full breakdown.",
    placement: "right",
  },
  {
    selector: 'a[href="/applicant/applications"]',
    title: "Every job you've sent, in one place",
    body: "Status, employer views, interview times you need to answer. This is where you'll spend most of your time once you start applying.",
    placement: "right",
  },
  {
    selector: 'a[href="/applicant/credentials"]',
    title: "Your credentials",
    body: "Add your OSHA, CDL, NCCER card, or a degree. We check them against the real registries so employers see a verified badge instead of your word for it.",
    placement: "right",
  },
  {
    selector: '[aria-label^="Notifications"]',
    title: "How we reach you",
    body: "New match, employer message, interview request. We only ping you when something needs a decision — you set the rest in Account.",
    placement: "bottom",
  },
];

export function CoachMarkTour({ displayName }: { displayName?: string | null }) {
  const [active, setActive] = useState(false);
  const [stepIx, setStepIx] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [showIntro, setShowIntro] = useState(true);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (localStorage.getItem(KEY)) return;
    setActive(true);
  }, []);

  // Track anchor position — retries every frame briefly until the sidebar has
  // hydrated & the target exists, then re-measures on resize/scroll.
  useLayoutEffect(() => {
    if (!active || showIntro) return;
    let cancel = false;

    function measure() {
      const step = STEPS[stepIx];
      if (!step) return;
      const el = document.querySelector<HTMLElement>(step.selector);
      if (el) {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) {
          setRect(r);
          return;
        }
      }
      if (!cancel) raf.current = requestAnimationFrame(measure);
    }
    measure();
    const onResize = () => measure();
    window.addEventListener("resize", onResize);
    window.addEventListener("scroll", onResize, true);
    return () => {
      cancel = true;
      if (raf.current) cancelAnimationFrame(raf.current);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onResize, true);
    };
  }, [active, stepIx, showIntro]);

  function dismiss() {
    localStorage.setItem(KEY, new Date().toISOString());
    setActive(false);
  }

  function next() {
    if (stepIx >= STEPS.length - 1) dismiss();
    else setStepIx((v) => v + 1);
  }

  if (!active) return null;

  // Intro card — no anchor, just centered card. Explains what's about to happen.
  if (showIntro) {
    return (
      <div className="fixed inset-0 z-[75] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Welcome tour">
        <div className="absolute inset-0 bg-studio-dark-cork/50 backdrop-blur-sm" onClick={dismiss} />
        <div className="relative w-full max-w-md rounded-xl border border-hairline bg-white p-7 shadow-[0_32px_64px_-24px_rgba(12,10,9,0.32)]">
          <button
            onClick={dismiss} aria-label="Skip tour"
            className="absolute right-3 top-3 rounded-md p-1 text-slate-muted hover:bg-stone/60 hover:text-cohere-ink"
          >
            <X className="h-4 w-4" />
          </button>
          <MonoLabel className="text-studio-maroon">Welcome{displayName ? `, ${displayName.split(" ")[0]}` : ""}</MonoLabel>
          <h2 className="mt-3 font-display text-heading text-cohere-ink">Four things to know.</h2>
          <p className="mt-3 text-body text-slate">
            Takes about a minute. If you'd rather explore on your own, hit Skip.
          </p>
          <div className="mt-6 flex items-center justify-between">
            <button onClick={dismiss} className="text-caption text-slate hover:text-cohere-ink">
              Skip
            </button>
            <button onClick={() => setShowIntro(false)} className="btn-primary inline-flex items-center gap-1.5">
              Show me <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  const step = STEPS[stepIx];
  const placement = step.placement ?? "right";

  // Fallback: if we couldn't find the element (small viewport, sidebar closed),
  // just dismiss silently so we never trap the user.
  if (!rect) {
    return null;
  }

  const spotlightPad = 6;
  const cutout = {
    top: rect.top - spotlightPad,
    left: rect.left - spotlightPad,
    width: rect.width + spotlightPad * 2,
    height: rect.height + spotlightPad * 2,
  };

  const tooltipStyle: React.CSSProperties = (() => {
    const gap = 12;
    if (placement === "right") {
      return { top: rect.top - 8, left: rect.right + gap };
    }
    if (placement === "bottom") {
      return { top: rect.bottom + gap, right: 16 };
    }
    return { top: rect.top - gap, left: rect.left };  // top
  })();

  return (
    <div className="fixed inset-0 z-[75] pointer-events-none" role="dialog" aria-modal="true" aria-label={`Tour step ${stepIx + 1}`}>
      {/* Dark scrim with a hollow rectangle around the anchor */}
      <div
        onClick={dismiss}
        className="absolute pointer-events-auto rounded-md"
        style={{
          top: cutout.top, left: cutout.left, width: cutout.width, height: cutout.height,
          boxShadow: "0 0 0 9999px rgba(12,10,9,0.55)",
          transition: "top 200ms ease, left 200ms ease, width 200ms ease, height 200ms ease",
        }}
      />

      {/* Tooltip card */}
      <div
        className="pointer-events-auto absolute w-[320px] max-w-[92vw] rounded-xl border border-hairline bg-white p-5 shadow-[0_24px_48px_-20px_rgba(12,10,9,0.35)]"
        style={tooltipStyle}
      >
        <div className="flex items-baseline justify-between gap-3">
          <span className="mono-label text-studio-maroon">Step {stepIx + 1} of {STEPS.length}</span>
          <button
            onClick={dismiss} aria-label="Dismiss tour"
            className="rounded-md p-0.5 text-slate-muted hover:text-cohere-ink"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <h3 className="mt-2 font-display text-feature text-cohere-ink">{step.title}</h3>
        <p className="mt-2 text-caption text-slate">{step.body}</p>

        <div className="mt-5 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            {STEPS.map((_, i) => (
              <span
                key={i}
                className={`h-1.5 rounded-full transition-all ${i === stepIx ? "w-6 bg-studio-dark-cork" : "w-1.5 bg-stone"}`}
              />
            ))}
          </div>
          <div className="flex items-center gap-2">
            {stepIx > 0 && (
              <button onClick={() => setStepIx((v) => v - 1)} className="text-caption text-slate hover:text-cohere-ink">
                Back
              </button>
            )}
            <button onClick={next} className="btn-primary inline-flex items-center gap-1.5">
              {stepIx < STEPS.length - 1 ? <>Next <ArrowRight className="h-4 w-4" /></> : "Done"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
