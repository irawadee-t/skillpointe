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

// How far the gas may drift past the nominal bubble edge. The falloff mask
// ends at 1.2R, so 1.3 leaves a small margin without wasted canvas.
const BLEED = 1.3;

// The hero orb's palette, exactly: the deep-red water sphere from the landing
// and auth pages. All clouds live in the #9d2235 red/maroon family with one
// warm glint — no green, no gold — so the mark IS the hero orb at every size.
// Opacities pushed toward 1 so the sphere reads dense and glossy, not fuzzy,
// even at 20px.
const CLOUDS: Array<{ color: string; fx: number; fy: number; ph: number; r: number }> = [
  { color: "rgba(157, 34, 53, 1)",      fx: 0.9,  fy: 1.3,  ph: 0.0, r: 0.95 }, // brand red (#9d2235)
  { color: "rgba(88, 16, 32, 0.98)",    fx: 1.15, fy: 0.75, ph: 2.1, r: 0.9  }, // deep maroon shadow
  { color: "rgba(178, 42, 58, 0.9)",   fx: 0.7,  fy: 1.05, ph: 4.2, r: 0.65 }, // ember highlight
  { color: "rgba(255, 235, 235, 0.45)",  fx: 1.35, fy: 0.95, ph: 5.3, r: 0.35 }, // small warm glint
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

  // base coat — a solid deep-red disc under the drifting clouds. Guarantees
  // the silhouette stays dense wherever the clouds have drifted, so the mark
  // never thins to a pale fuzz at avatar sizes.
  let g = ctx.createRadialGradient(c, c, 0, c, c, R * 1.05);
  g.addColorStop(0, "rgba(110, 20, 36, 1)");
  g.addColorStop(0.85, "rgba(110, 20, 36, 1)");
  g.addColorStop(1, "rgba(110, 20, 36, 0)");
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

  // specular highlight — small warm-white glint offset to the top-left,
  // the glossy cue that turns the gas into a wet sphere.
  const hx = c - R * 0.3;
  const hy = c - R * 0.3;
  g = ctx.createRadialGradient(hx, hy, 0, hx, hy, R * 0.38);
  g.addColorStop(0, "rgba(255, 248, 240, 0.75)");
  g.addColorStop(0.4, "rgba(255, 240, 228, 0.28)");
  g.addColorStop(1, "rgba(255, 240, 228, 0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);

  // film grain — quiet texture only; kept low so small orbs stay solid
  ctx.globalCompositeOperation = "overlay";
  ctx.globalAlpha = 0.12;
  const grain = getGrain();
  for (let gx = 0; gx < S; gx += 96) {
    for (let gy = 0; gy < S; gy += 96) {
      ctx.drawImage(grain, gx, gy);
    }
  }
  ctx.globalAlpha = 1;

  // density falloff — THE edge. Fully dense to ~0.85R, gone by ~1.2R, so the
  // silhouette reads as a round solid sphere with only a short atmospheric
  // trail. destination-in keeps the edge a falloff, not a hard crop.
  ctx.globalCompositeOperation = "destination-in";
  g = ctx.createRadialGradient(c, c, 0, c, c, R * 1.2);
  g.addColorStop(0, "rgba(0,0,0,1)");
  g.addColorStop(0.7, "rgba(0,0,0,1)");     // 0.85R — fully dense
  g.addColorStop(0.87, "rgba(0,0,0,0.45)"); // ~1.05R — falling fast
  g.addColorStop(1, "rgba(0,0,0,0)");       // 1.2R — gone
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
