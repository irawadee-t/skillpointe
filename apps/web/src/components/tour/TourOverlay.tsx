"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowRight, X } from "lucide-react";
import type { Tour } from "@/lib/tours";

/**
 * Spotlight coach-mark overlay — renders ONE step of a tour.
 *
 * Anchoring: the step's selector is scanned every frame until a VISIBLE match
 * exists (drawer/sidebar can render the same link twice; streamed sections
 * arrive late). The match is scrolled into view, then the spotlight cutout and
 * card track it through scroll and resize. If nothing shows up within the
 * give-up window the step is skipped rather than rendering a dead overlay.
 *
 * Non-blocking by design: the scrim never captures clicks (it is drawn with a
 * box-shadow, which cannot intercept events), Esc always exits, and the card
 * is the only focus surface.
 */

const GIVE_UP_MS = 3000;
const SPOT_PAD = 6;
const GAP = 12;
const MARGIN = 12;

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

type Pos = { top: number; left: number };

function placeCard(
  anchor: DOMRect,
  card: { width: number; height: number },
  preferred: "top" | "bottom" | "left" | "right",
  vw: number,
  vh: number,
): Pos {
  const fits = (p: Pos) =>
    p.top >= MARGIN &&
    p.left >= MARGIN &&
    p.top + card.height <= vh - MARGIN &&
    p.left + card.width <= vw - MARGIN;

  const centeredX = anchor.left + anchor.width / 2 - card.width / 2;
  const centeredY = anchor.top + anchor.height / 2 - card.height / 2;
  const candidates: Record<string, Pos> = {
    bottom: { top: anchor.bottom + GAP, left: centeredX },
    top: { top: anchor.top - GAP - card.height, left: centeredX },
    right: { top: centeredY, left: anchor.right + GAP },
    left: { top: centeredY, left: anchor.left - GAP - card.width },
  };

  const order = [preferred, "bottom", "top", "right", "left"].filter(
    (v, i, a) => a.indexOf(v) === i,
  ) as Array<"top" | "bottom" | "left" | "right">;

  // First pass: any side that fully fits after clamping the cross axis.
  for (const side of order) {
    const p = { ...candidates[side] };
    p.left = Math.min(Math.max(p.left, MARGIN), vw - card.width - MARGIN);
    p.top = Math.min(Math.max(p.top, MARGIN), vh - card.height - MARGIN);
    const raw = candidates[side];
    const mainAxisOk =
      side === "bottom" ? raw.top + card.height <= vh - MARGIN
      : side === "top" ? raw.top >= MARGIN
      : side === "right" ? raw.left + card.width <= vw - MARGIN
      : raw.left >= MARGIN;
    if (mainAxisOk && fits(p)) return p;
  }

  // Fallback (small screens): clamp fully inside the viewport, below if room.
  const below = anchor.bottom + GAP + card.height <= vh - MARGIN;
  return {
    top: below
      ? anchor.bottom + GAP
      : Math.max(MARGIN, vh - card.height - MARGIN),
    left: Math.min(Math.max(centeredX, MARGIN), Math.max(MARGIN, vw - card.width - MARGIN)),
  };
}

export function TourOverlay({
  tour,
  stepIx,
  onNext,
  onBack,
  onExit,
  onSkipMissing,
}: {
  tour: Tour;
  stepIx: number;
  onNext: () => void;
  onBack: () => void;
  onExit: () => void;
  /** Anchor never became visible — advance past this step. */
  onSkipMissing: () => void;
}) {
  const step = tour.steps[stepIx];
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [cardPos, setCardPos] = useState<Pos | null>(null);
  const reduced = usePrefersReducedMotion();
  const cardRef = useRef<HTMLDivElement | null>(null);
  const anchorRef = useRef<HTMLElement | null>(null);
  const scrolledRef = useRef(false);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  // Remember and restore focus around the whole overlay lifetime.
  useEffect(() => {
    restoreFocusRef.current = (document.activeElement as HTMLElement) ?? null;
    return () => restoreFocusRef.current?.focus?.();
  }, []);

  // Find + track the anchor for the current step.
  useLayoutEffect(() => {
    if (!step) return;
    let cancelled = false;
    let raf: number | null = null;
    anchorRef.current = null;
    scrolledRef.current = false;
    setRect(null);
    setCardPos(null);

    const measure = () => {
      if (cancelled) return;
      let el = anchorRef.current;
      if (!el || !el.isConnected) {
        el = null;
        const matches = document.querySelectorAll<HTMLElement>(step.anchor);
        for (const m of matches) {
          const r = m.getBoundingClientRect();
          if (r.width > 0 && r.height > 0) {
            el = m;
            break;
          }
        }
        anchorRef.current = el;
      }
      if (el) {
        if (!scrolledRef.current) {
          scrolledRef.current = true;
          const r = el.getBoundingClientRect();
          const outside = r.top < 72 || r.bottom > window.innerHeight - 72;
          if (outside) {
            el.scrollIntoView({
              block: "center",
              inline: "nearest",
              behavior: reduced ? "auto" : "smooth",
            });
          }
        }
        setRect(el.getBoundingClientRect());
        // Keep following while smooth scroll settles.
        raf = requestAnimationFrame(measure);
        return;
      }
      raf = requestAnimationFrame(measure);
    };
    measure();

    const giveUp = window.setTimeout(() => {
      if (!cancelled && !anchorRef.current) onSkipMissing();
    }, GIVE_UP_MS);

    return () => {
      cancelled = true;
      if (raf !== null) cancelAnimationFrame(raf);
      window.clearTimeout(giveUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepIx, tour.id, step?.anchor, reduced]);

  // Position the card once we know both rects; re-run when the anchor moves.
  useLayoutEffect(() => {
    if (!rect || !cardRef.current) return;
    const c = cardRef.current.getBoundingClientRect();
    setCardPos(
      placeCard(
        rect,
        { width: c.width, height: c.height },
        step?.placement ?? "bottom",
        window.innerWidth,
        window.innerHeight,
      ),
    );
  }, [rect, stepIx, step?.placement]);

  // Move focus into the card on each step.
  useEffect(() => {
    if (!rect) return;
    const t = window.setTimeout(() => cardRef.current?.focus(), 30);
    return () => window.clearTimeout(t);
  }, [rect === null, stepIx]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keyboard: Esc exits, arrows navigate, Tab stays inside the card.
  const onKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onExit();
        return;
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        onNext();
        return;
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        if (stepIx > 0) onBack();
        return;
      }
      if (e.key === "Tab") {
        const root = cardRef.current;
        if (!root) return;
        const focusables = root.querySelectorAll<HTMLElement>(
          'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (!root.contains(active)) {
          e.preventDefault();
          first.focus();
        } else if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    },
    [onExit, onNext, onBack, stepIx],
  );
  useEffect(() => {
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onKeyDown]);

  if (!step || !rect) return null;

  const cutout = {
    top: rect.top - SPOT_PAD,
    left: rect.left - SPOT_PAD,
    width: rect.width + SPOT_PAD * 2,
    height: rect.height + SPOT_PAD * 2,
  };
  const spotTransition = reduced
    ? undefined
    : "top 200ms ease, left 200ms ease, width 200ms ease, height 200ms ease";
  const isLast = stepIx >= tour.steps.length - 1;

  return (
    <div
      className="fixed inset-0 z-[75] pointer-events-none"
      role="dialog"
      aria-modal="true"
      aria-label={`${tour.label}, step ${stepIx + 1} of ${tour.steps.length}`}
    >
      {/* Scrim with a hollow rectangle over the anchor. The shadow cannot
          capture clicks, so the rest of the page stays usable. */}
      <div
        aria-hidden
        className="absolute rounded-md"
        style={{
          top: cutout.top,
          left: cutout.left,
          width: cutout.width,
          height: cutout.height,
          boxShadow: "0 0 0 9999px rgba(12,10,9,0.55)",
          transition: spotTransition,
        }}
      />

      {/* Card — quiet white sheet, hairline border. Hidden until placed so the
          first paint never flashes in the wrong corner. */}
      <div
        ref={cardRef}
        tabIndex={-1}
        className="pointer-events-auto absolute w-[min(320px,calc(100vw-24px))] rounded-xl border border-hairline bg-white p-5 shadow-float outline-none"
        style={{
          top: cardPos?.top ?? -9999,
          left: cardPos?.left ?? -9999,
          visibility: cardPos ? "visible" : "hidden",
          transition: reduced || !cardPos ? undefined : "top 200ms ease, left 200ms ease",
        }}
      >
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-micro font-medium tabular-nums text-slate-muted">
            {stepIx + 1} of {tour.steps.length}
          </span>
          <button
            onClick={onExit}
            aria-label="Exit tour"
            className="rounded-md p-0.5 text-slate-muted transition-colors hover:text-cohere-ink"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <h3 className="mt-2 text-[1.0625rem] font-medium text-cohere-ink">{step.title}</h3>
        <p className="mt-1.5 text-caption text-slate">{step.body}</p>

        <div className="mt-5 flex items-center justify-between">
          <div className="flex items-center gap-1.5" aria-hidden>
            {tour.steps.map((_, i) => (
              <span
                key={i}
                className={`h-1.5 rounded-full ${
                  reduced ? "" : "transition-[width,background-color] duration-200"
                } ${i === stepIx ? "w-6 bg-ink" : "w-1.5 bg-stone"}`}
              />
            ))}
          </div>
          <div className="flex items-center gap-2">
            {stepIx > 0 && (
              <button
                onClick={onBack}
                className="text-caption text-slate transition-colors hover:text-cohere-ink"
              >
                Back
              </button>
            )}
            <button onClick={onNext} className="btn-primary inline-flex items-center gap-1.5">
              {isLast ? "Done" : (
                <>
                  Next <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
