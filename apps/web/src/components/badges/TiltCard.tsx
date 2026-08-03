"use client";

import { useCallback, useRef } from "react";
import { useReducedMotion } from "motion/react";

const MAX_TILT = 8; // degrees — deliberately half of the Comet Card reference

/**
 * A scoped 3D-tilt wrapper. Per DESIGN_CONTRACT.md this is permitted ONLY on
 * badge showcase cards — content and list cards stay flat.
 *
 * The transform is written straight to the node (no React state, no re-render
 * per pointer move) and eased by a CSS transition: a short spring-ish curve
 * while tracking, a longer one on release so the card settles rather than
 * snaps.
 *
 * Guards:
 *  - disabled under prefers-reduced-motion — `useReducedMotion()` reads the
 *    same preference the app-wide MotionConfig honours
 *  - pointer-only: coarse pointers (touch/pen) never tilt
 */
const TRACK_EASE = "transform 90ms cubic-bezier(0.33, 1, 0.68, 1)";
const SETTLE_EASE = "transform 500ms cubic-bezier(0.22, 1.2, 0.36, 1)";

export function TiltCard({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();
  const enabled = !reduced;

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (e.pointerType !== "mouse") return;
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5; // -0.5 … 0.5
      const py = (e.clientY - r.top) / r.height - 0.5;
      const rotateY = px * MAX_TILT * 2;
      const rotateX = -py * MAX_TILT * 2;
      el.style.transition = TRACK_EASE;
      el.style.transform = `rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg)`;
    },
    [],
  );

  const reset = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.transition = SETTLE_EASE;
    el.style.transform = "rotateX(0deg) rotateY(0deg)";
  }, []);

  if (!enabled) return <div className={className}>{children}</div>;

  return (
    <div style={{ perspective: 900 }} className="h-full">
      <div
        ref={ref}
        onPointerMove={handlePointerMove}
        onPointerLeave={reset}
        onPointerCancel={reset}
        style={{ transformStyle: "preserve-3d", willChange: "transform" }}
        className={className}
      >
        {children}
      </div>
    </div>
  );
}
