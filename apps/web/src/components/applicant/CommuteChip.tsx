"use client";

import { useEffect, useState } from "react";
import { Clock, Car } from "lucide-react";

import { Commute, commuteForMatch } from "@/lib/api/robustness";
import { cn } from "@/lib/utils";

type Tone = "on-dark" | "on-light";

/**
 * Drive-time indicator for a specific match. Two visual modes:
 *   • on-dark  — sits inside the green hero next to the MapPin location row.
 *                Matches the existing "icon + text-white/80" rhythm so it
 *                reads as another location fact, not a foreign chip.
 *   • on-light — pill on white surfaces (e.g. match list cards).
 *
 * Renders nothing until we have a resolved commute (soft skeleton while loading),
 * and renders a subtle "add your city" nudge if the applicant profile is missing
 * location — no error state, no red flags.
 */
export function CommuteChip({
  token, matchId, tone = "on-dark",
}: { token: string; matchId: string; tone?: Tone }) {
  const [data, setData] = useState<Commute | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    commuteForMatch(token, matchId)
      .then((c) => { if (alive) setData(c); })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [token, matchId]);

  if (failed) return null;

  // Loading — a whisper-thin skeleton that matches the row height, so nothing shifts.
  if (!data) {
    return (
      <span className={cn(
        "inline-flex items-center gap-1.5",
        tone === "on-dark" ? "text-white/40" : "text-slate-muted",
      )}>
        <Clock className="h-3.5 w-3.5" strokeWidth={1.75} />
        <span className={cn(
          "h-3 w-16 animate-pulse rounded-sm",
          tone === "on-dark" ? "bg-white/15" : "bg-stone",
        )} />
      </span>
    );
  }

  // Unavailable (missing profile city, etc.) — quiet nudge.
  if (data.minutes == null) {
    if (!data.unavailable_reason) return null;
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 text-caption",
          tone === "on-dark" ? "text-white/60" : "text-slate-muted",
        )}
        title={data.unavailable_reason}
      >
        <Clock className="h-3.5 w-3.5" strokeWidth={1.75} />
        Drive time unavailable
      </span>
    );
  }

  const { text, hint } = formatDriveTime(data.minutes, data.provider);

  // Inline row mode — matches existing location cluster on the hero.
  if (tone === "on-dark") {
    return (
      <span className="inline-flex items-center gap-1" title={hint}>
        <Car className="h-3.5 w-3.5 text-white/60" strokeWidth={1.75} />
        <span className="text-body text-white/80">{text}</span>
      </span>
    );
  }

  // Pill for light surfaces (match list cards).
  return (
    <span
      title={hint}
      className="inline-flex items-center gap-1 rounded-full border border-hairline bg-white px-2.5 py-0.5 text-micro text-slate"
    >
      <Car className="h-3 w-3 text-slate-muted" strokeWidth={1.75} />
      {text}
    </span>
  );
}

function formatDriveTime(minutes: number, provider: string): { text: string; hint: string } {
  // Human-natural buckets — no decimals past 90 min.
  let text: string;
  if (minutes < 60) {
    text = `${minutes} min drive`;
  } else if (minutes < 90) {
    // 1 hr, 1 hr 15 min, 1 hr 30 min
    const h = Math.floor(minutes / 60);
    const remainder = Math.round((minutes - h * 60) / 15) * 15;
    text = remainder === 0 ? `${h} hr drive` : `${h} hr ${remainder} min drive`;
  } else if (minutes < 60 * 8) {
    text = `${Math.round(minutes / 60)} hr drive`;
  } else {
    // Very long — signal it's cross-country without giving false precision.
    text = "Long drive — plan travel";
  }

  const providerNote: Record<string, string> = {
    google:    "Live drive time from Google Maps",
    mapbox:    "Live drive time from Mapbox",
    cached:    "Cached drive time",
    haversine: "Estimated from distance — add a Google or Mapbox key for real drive times",
  };
  return { text, hint: providerNote[provider] ?? "Approximate drive time" };
}
