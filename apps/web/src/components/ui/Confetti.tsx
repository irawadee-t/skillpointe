"use client";

import { useEffect, useRef } from "react";

/**
 * Lightweight, dependency-free confetti burst. Mounts a fixed-position canvas
 * that fills the viewport, fires a one-time burst of ~180 particles, then
 * self-unmounts once the last particle has fallen off screen.
 *
 * Respects prefers-reduced-motion — becomes a no-op.
 */
export function Confetti({ active }: { active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const doneRef = useRef(false);

  useEffect(() => {
    if (!active || doneRef.current) return;
    doneRef.current = true;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx: CanvasRenderingContext2D | null = canvas.getContext("2d");
    if (!ctx) return;
    const ctx2 = ctx;   // non-null alias for the closure — TS narrows inside the effect but not inside `tick`

    const dpr = window.devicePixelRatio || 1;
    const w = canvas.width  = window.innerWidth * dpr;
    const h = canvas.height = window.innerHeight * dpr;
    canvas.style.width  = window.innerWidth + "px";
    canvas.style.height = window.innerHeight + "px";
    ctx2.scale(dpr, dpr);

    const COLORS = ["#116339", "#0F8B4C", "#EF6C4A", "#F8CD91", "#0C0A08"]; // green, green, coral, cream, ink
    const particles: {
      x: number; y: number; vx: number; vy: number; rot: number; vrot: number;
      size: number; color: string; life: number;
    }[] = [];

    const N = 180;
    for (let i = 0; i < N; i++) {
      particles.push({
        x: window.innerWidth / 2 + (Math.random() - 0.5) * 60,
        y: window.innerHeight / 3,
        vx: (Math.random() - 0.5) * 12,
        vy: -Math.random() * 12 - 4,
        rot: Math.random() * Math.PI,
        vrot: (Math.random() - 0.5) * 0.3,
        size: 6 + Math.random() * 6,
        color: COLORS[Math.floor(Math.random() * COLORS.length)],
        life: 1,
      });
    }

    let raf = 0;
    const start = performance.now();
    function tick(now: number) {
      const dt = 1 / 60;
      ctx2.clearRect(0, 0, w, h);
      let alive = 0;
      for (const p of particles) {
        p.vy += 24 * dt;                 // gravity
        p.vx *= 0.995;                   // air drag
        p.x += p.vx;
        p.y += p.vy;
        p.rot += p.vrot;
        p.life = Math.max(0, 1 - (now - start) / 3800);
        if (p.y < window.innerHeight + 40 && p.life > 0) {
          alive++;
          ctx2.save();
          ctx2.translate(p.x, p.y);
          ctx2.rotate(p.rot);
          ctx2.fillStyle = p.color;
          ctx2.globalAlpha = Math.min(1, p.life * 1.6);
          ctx2.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
          ctx2.restore();
        }
      }
      if (alive > 0) raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active]);

  if (!active) return null;
  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none fixed inset-0 z-[80]"
    />
  );
}
