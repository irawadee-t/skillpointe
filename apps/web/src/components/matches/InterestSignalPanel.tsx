"use client";

/**
 * InterestSignalPanel — applicant sets their intent for a job match.
 *
 * Three states (plus none):
 *   interested     → "Interested" / "Planning to apply" (no URL)
 *   applied        → "Applied externally" / "I've applied" (no URL)  ← also logs apply_click
 *   not_interested → "Not interested"
 *
 * Clicking the already-active pill CLEARS the selection (back to none) —
 * the backend deletes the saved_jobs row when interest_level is null.
 *
 * When the job has a source_url, the "Apply externally" link is shown
 * and auto-sets the state to "applied" on click.
 * When there is no source_url, the three buttons are shown prominently
 * with labels appropriate for a self-reported status.
 *
 * Can run uncontrolled (manages its own state, default) or controlled:
 * pass `signal` + `onSignalChange` and the parent owns the current value —
 * used by the matches list to hide/restore cards on "Not interested".
 */
import { useState } from "react";
import {
  CheckCircle2,
  ThumbsDown,
  ThumbsUp,
  Loader2,
} from "lucide-react";

import { useViewAs, VIEW_AS_READONLY_TOOLTIP } from "@/hooks/useViewAs";

export type InterestLevel = "interested" | "applied" | "not_interested";

interface InterestSignalPanelProps {
  matchId: string;
  sourceUrl: string | null;
  initialSignal: InterestLevel | null;
  token: string;
  /** Controlled mode: current signal owned by the parent. */
  signal?: InterestLevel | null;
  /** Called after a successful save with (next, previous). */
  onSignalChange?: (next: InterestLevel | null, previous: InterestLevel | null) => void;
}

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

/** POST the interest signal (null clears it). Shared with the matches list undo. */
export async function setMatchInterest(
  token: string,
  matchId: string,
  level: InterestLevel | null,
): Promise<void> {
  const res = await fetch(`${API_URL}/applicant/me/matches/${matchId}/interest`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ interest_level: level }),
  });
  if (!res.ok) throw new Error("Failed to save");
}

export function InterestSignalPanel({
  matchId,
  sourceUrl,
  initialSignal,
  token,
  signal,
  onSignalChange,
}: InterestSignalPanelProps) {
  const [internal, setInternal] = useState<InterestLevel | null>(initialSignal);
  const [loading, setLoading] = useState<InterestLevel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { isViewAs } = useViewAs();

  const controlled = signal !== undefined;
  const current = controlled ? signal : internal;

  async function handleSelect(level: InterestLevel) {
    if (loading) return;
    // Clicking the active pill clears the selection.
    const next: InterestLevel | null = current === level ? null : level;
    setLoading(level);
    setError(null);
    try {
      await setMatchInterest(token, matchId, next);
      if (!controlled) setInternal(next);
      onSignalChange?.(next, current ?? null);
    } catch {
      setError("Could not save. Please try again.");
    } finally {
      setLoading(null);
    }
  }

  // Labels differ based on whether there's an external apply link
  const hasUrl = Boolean(sourceUrl);

  const LEVELS: {
    value: InterestLevel;
    label: string;
    icon: React.ElementType;
    activeClass: string;
  }[] = [
    // Hues mirror the employer's ApplicantInterestBadge — applied = green,
    // interested = blue, not interested = neutral. One hue per meaning.
    {
      value: "interested",
      label: hasUrl ? "Interested" : "Planning to apply",
      icon: ThumbsUp,
      activeClass: "bg-cohere-blue border-cohere-blue text-white",
    },
    {
      value: "applied",
      label: hasUrl ? "Applied externally" : "I've applied",
      icon: CheckCircle2,
      activeClass: "bg-cohere-green border-cohere-green text-white",
    },
    {
      value: "not_interested",
      label: "Not interested",
      icon: ThumbsDown,
      activeClass: "bg-ink border-cohere-ink text-white",
    },
  ];

  // Show a soft nudge after Apply-externally click if the user has NOT set a signal.
  // We optimistically auto-set "applied", but if the network write fails or the
  // user closes the tab first, we still ask them to confirm on return.
  const needsNudge = hasUrl && current === null;

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-caption text-slate-muted">
          {hasUrl ? "Your interest" : "Your status"}
        </span>

        <div className="flex flex-wrap gap-1.5">
          {LEVELS.map(({ value, label, icon: Icon, activeClass }) => {
            const active = current === value;
            return (
              <button
                key={value}
                onClick={() => handleSelect(value)}
                disabled={loading !== null || isViewAs}
                aria-pressed={active}
                title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : active ? "Click again to clear" : undefined}
                className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[12px] transition-[color,background-color,border-color,transform] duration-150 ease-cohere active:scale-[0.96] ${
                  active
                    ? activeClass
                    : "border-hairline bg-white text-slate hover:border-cohere-ink hover:text-cohere-ink"
                }`}
              >
                {loading === value ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Icon className="h-3 w-3" />
                )}
                {label}
              </button>
            );
          })}
        </div>

        {error && <span className="text-[12px] text-error-red">{error}</span>}
      </div>

      {/* Soft nudge until they pick — quiet, useful, then gone */}
      {needsNudge && (
        <p className="text-micro text-slate-muted">
          Pick one. It sharpens what we show you next.
        </p>
      )}
    </div>
  );
}
