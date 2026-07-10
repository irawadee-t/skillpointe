"use client";

/**
 * Orb — the platform's living mark: a bubble of colored gas (ElevenLabs
 * spirit). The core is dense and round, but the gas doesn't stop at the
 * silhouette — it thins and wisps past the edge. No hard crop anywhere:
 * the boundary is a density falloff, not a clipping path.
 *
 *   <OrbMark />     — at rest: slow atmospheric drift. Never still.
 *   <ThinkingOrb /> — working: the same weather, ~4× faster, breathing.
 *
 * Canvas 2D. The canvas is drawn larger than the layout box and centered,
 * so the bleed overflows without shifting layout. Honors
 * prefers-reduced-motion (one static frame).
 */

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

// How far the gas may drift past the nominal bubble edge.
const BLEED = 1.7;

// Pastelized brand palette — gas, not pigment.
const CLOUDS: Array<{ color: string; fx: number; fy: number; ph: number; r: number }> = [
  { color: "rgba(200, 62, 88, 0.95)",   fx: 0.9,  fy: 1.3,  ph: 0.0, r: 0.9  }, // rose (maroon, lifted)
  { color: "rgba(128, 134, 70, 0.95)",  fx: 1.15, fy: 0.75, ph: 2.1, r: 0.95 }, // sage (olive, lifted)
  { color: "rgba(232, 110, 40, 0.9)",   fx: 0.7,  fy: 1.05, ph: 4.2, r: 0.8  }, // peach (sienna, lifted)
  { color: "rgba(255, 238, 214, 0.55)", fx: 1.35, fy: 0.95, ph: 5.3, r: 0.4  }, // small warm glint
];

// Shared static grain tile — the film texture that keeps the gas from
// reading as a smooth ombre.
let grainTile: HTMLCanvasElement | null = null;
function getGrain(): HTMLCanvasElement {
  if (grainTile) return grainTile;
  const g = document.createElement("canvas");
  g.width = 96;
  g.height = 96;
  const gctx = g.getContext("2d")!;
  const img = gctx.createImageData(96, 96);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = 128 + (Math.random() - 0.5) * 255;
    img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
    img.data[i + 3] = 255;
  }
  gctx.putImageData(img, 0, 0);
  grainTile = g;
  return g;
}

function draw(ctx: CanvasRenderingContext2D, canvasSize: number, orbSize: number, t: number, breathe: number) {
  const S = canvasSize;
  const c = S / 2;
  const R = (orbSize / 2) * (1 + breathe); // nominal bubble radius

  ctx.clearRect(0, 0, S, S);

  // luminous core — a glow, not a disc
  let g = ctx.createRadialGradient(c, c, 0, c, c, R * 1.3);
  g.addColorStop(0, "rgba(236, 210, 184, 0.95)");
  g.addColorStop(0.75, "rgba(236, 210, 184, 0.55)");
  g.addColorStop(1, "rgba(236, 210, 184, 0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);

  // drifting gas clouds — free to cross the boundary
  for (const f of CLOUDS) {
    const x = c + Math.sin(t * f.fx + f.ph) * R * 0.55;
    const y = c + Math.cos(t * f.fy + f.ph * 1.7) * R * 0.55;
    const rad = R * f.r * (1.15 + 0.18 * Math.sin(t * 0.7 + f.ph));
    g = ctx.createRadialGradient(x, y, 0, x, y, rad);
    g.addColorStop(0, f.color);
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, S, S);
  }

  // film grain — fades out with the gas via the mask below
  ctx.globalCompositeOperation = "overlay";
  ctx.globalAlpha = 0.4;
  const grain = getGrain();
  for (let gx = 0; gx < S; gx += 96) {
    for (let gy = 0; gy < S; gy += 96) {
      ctx.drawImage(grain, gx, gy);
    }
  }
  ctx.globalAlpha = 1;

  // density falloff — THE edge. Fully dense to ~0.7R, gone by ~1.55R.
  // destination-in keeps the bubble reading as a bubble while letting the
  // gas trail past the silhouette instead of being sheared off.
  ctx.globalCompositeOperation = "destination-in";
  g = ctx.createRadialGradient(c, c, 0, c, c, R * 1.55);
  g.addColorStop(0, "rgba(0,0,0,1)");
  g.addColorStop(0.45, "rgba(0,0,0,1)");
  g.addColorStop(0.68, "rgba(0,0,0,0.82)");
  g.addColorStop(0.85, "rgba(0,0,0,0.35)");
  g.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);
  ctx.globalCompositeOperation = "source-over";
}

function OrbBase({
  size,
  speed,
  breathing,
  className,
  label,
}: {
  size: number;
  speed: number;
  breathing?: boolean;
  className?: string;
  label?: string;
}) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const canvasSize = Math.ceil(size * BLEED);
  const offset = (canvasSize - size) / 2;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = canvasSize * dpr;
    canvas.height = canvasSize * dpr;
    ctx.scale(dpr, dpr);

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Random start phase so a page of orbs doesn't move in lockstep.
    let t = Math.random() * 40;

    // First frame synchronously — the orb is never blank.
    draw(ctx, canvasSize, size, t, 0);

    if (reduced) return;

    let raf = 0;
    let last = performance.now();
    const frame = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;
      t += dt * speed;
      const breathe = breathing ? 0.045 * Math.sin(t * 2.4) : 0;
      draw(ctx, canvasSize, size, t, breathe);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [size, speed, breathing, canvasSize]);

  return (
    <span
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn("relative inline-block shrink-0 select-none", className)}
      style={{ width: size, height: size }}
    >
      <canvas
        ref={ref}
        aria-hidden
        className="pointer-events-none absolute"
        style={{ width: canvasSize, height: canvasSize, left: -offset, top: -offset }}
      />
    </span>
  );
}

export function OrbMark({
  size = 28,
  className,
  label,
}: {
  size?: number;
  className?: string;
  /** Set for standalone marks (e.g. "SKILLED assistant"); omit when decorative next to text. */
  label?: string;
}) {
  return <OrbBase size={size} speed={0.5} className={className} label={label} />;
}

export function ThinkingOrb({
  size = 28,
  className,
}: {
  size?: number;
  className?: string;
}) {
  // Decorative by design — the accompanying text ("Thinking…") carries meaning.
  return <OrbBase size={size} speed={2.1} breathing className={className} />;
}
