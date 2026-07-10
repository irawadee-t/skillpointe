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
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  as?: Tag;
  /** Fade only, no upward translate. */
  fade?: boolean;
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
      { threshold: 0.15, rootMargin: "0px 0px -8% 0px" },
    );
    io.observe(el);

    // Fallback: never leave content hidden if the observer never fires.
    const fallback = window.setTimeout(() => setVisible(true), 1400);

    return () => {
      io.disconnect();
      window.clearTimeout(fallback);
    };
  }, []);

  const Tag = as as React.ElementType;
  return (
    <Tag
      ref={ref}
      style={delay ? { transitionDelay: `${delay}s` } : undefined}
      className={cn("reveal", fade && "reveal-fade", visible && "is-visible", className)}
    >
      {children}
    </Tag>
  );
}
