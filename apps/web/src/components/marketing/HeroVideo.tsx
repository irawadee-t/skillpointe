"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Full-bleed hero background video.
 *
 * - Muted, autoplaying, looping (browser policy allows only when muted).
 * - Falls back to a static poster while the video loads OR if playback fails
 *   (e.g. reduced-motion preference, low-power mode on mobile Safari).
 * - Overlays a semi-opaque scrim so foreground text remains legible without
 *   forcing white text on a bright frame.
 *
 * Place the compressed video at `/video/hero.mp4` (and optionally
 * `/video/hero.webm`). Keep the poster image at `/video/hero-poster.jpg`.
 */
export function HeroVideo({
  className = "",
  scrim = "gradient",
}: {
  className?: string;
  /** Overlay strength: "none" | "light" | "gradient" | "heavy". */
  scrim?: "none" | "light" | "gradient" | "heavy";
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    // Respect reduced-motion — don't auto-play if the user opts out.
    const prefersReduce =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduce && videoRef.current) {
      videoRef.current.pause();
    }
  }, []);

  const scrimClass =
    scrim === "none"
      ? ""
      : scrim === "light"
        ? "bg-black/25"
        : scrim === "heavy"
          ? "bg-black/55"
          : "bg-gradient-to-b from-black/60 via-black/30 to-black/70";

  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`} aria-hidden="true">
      {/* Poster image sits under the video and paints first — no grey flash
          while the MP4 buffers, and no opacity fade to reveal what's already
          on-screen. As soon as the first frame is decoded the <video> element
          composites over it seamlessly. */}
      <img
        src="/video/hero-poster.jpg"
        alt=""
        className="absolute inset-0 h-full w-full object-cover"
        aria-hidden="true"
      />
      <video
        ref={videoRef}
        className="relative h-full w-full object-cover"
        autoPlay
        muted
        loop
        playsInline
        preload="auto"
        poster="/video/hero-poster.jpg"
      >
        <source src="/video/hero.mp4" type="video/mp4" />
      </video>
      {/* Overlay scrim to preserve foreground legibility */}
      <div className={`absolute inset-0 ${scrimClass}`} />
    </div>
  );
}
