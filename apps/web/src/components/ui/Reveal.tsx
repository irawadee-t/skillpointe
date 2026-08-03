"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

type Tag = "div" | "section" | "li" | "article" | "span";

/**
 * Scroll-triggered reveal — CSS/compositor driven so it never stalls under
 * rAF throttling (background tabs, low-power devices). Content is guaranteed
 * to become visible via an IntersectionObserver, with a timed fallback if the
 * observer never fires.
 */
export function Reveal({
  children,
  className,
  delay = 0,
  as = "div",
  fade = false,
  "data-tour-id": dataTourId,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  as?: Tag;
  /** Fade only, no upward translate. */
  fade?: boolean;
  /** Optional anchor id for the coach-mark tour system. */
  "data-tour-id"?: string;
}) {
  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }

    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true);
            io.disconnect();
            break;
          }
        }
      },
      // Reveal ONCE (io.disconnect above), triggered as soon as any pixel is
      // within the viewport + a generous 25% pre-roll below it — so content is
      // never a blank viewport under fast scrolling or anchor jumps; the small
      // 8px rise happens just before it comes into view.
      { threshold: 0, rootMargin: "0px 0px 25% 0px" },
    );
    io.observe(el);

    // Fallback: never leave content hidden if the observer never fires.
    const fallback = window.setTimeout(() => setVisible(true), 900);

    return () => {
      io.disconnect();
      window.clearTimeout(fallback);
    };
  }, []);

  const Tag = as as React.ElementType;
  return (
    <Tag
      ref={ref}
      data-tour-id={dataTourId}
      style={delay ? { transitionDelay: `${delay}s` } : undefined}
      className={cn("reveal", fade && "reveal-fade", visible && "is-visible", className)}
    >
      {children}
    </Tag>
  );
}
