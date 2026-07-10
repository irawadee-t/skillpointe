"use client";

/**
 * InterestSignalPanel — applicant sets their intent for a job match.
 *
 * Three states:
 *   interested     → "Interested" / "Planning to apply" (no URL)
 *   applied        → "Applied externally" / "I've applied" (no URL)  ← also logs apply_click
 *   not_interested → "Not interested"
 *
 * When the job has a source_url, the "Apply externally" link is shown
 * and auto-sets the state to "applied" on click.
 * When there is no source_url, the three buttons are shown prominently
 * with labels appropriate for a self-reported status.
 */
import { useState } from "react";
import {
  CheckCircle2,
  ThumbsDown,
  ThumbsUp,
  Loader2,
} from "lucide-react";

interface InterestSignalPanelProps {
  matchId: string;
  sourceUrl: string | null;
  initialSignal: "interested" | "applied" | "not_interested" | null;
  token: string;
}

type Level = "interested" | "applied" | "not_interested";

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

export function InterestSignalPanel({
  matchId,
  sourceUrl,
  initialSignal,
  token,
}: InterestSignalPanelProps) {
  const [current, setCurrent] = useState<Level | null>(initialSignal);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSelect(level: Level) {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/applicant/me/matches/${matchId}/interest`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ interest_level: level }),
      });
      if (!res.ok) throw new Error("Failed to save");
      setCurrent(level);
    } catch {
      setError("Could not save — please try again.");
    } finally {
      setLoading(false);
    }
  }

  // Labels differ based on whether there's an external apply link
  const hasUrl = Boolean(sourceUrl);

  const LEVELS: {
    value: Level;
    label: string;
    icon: React.ElementType;
    activeClass: string;
  }[] = [
    {
      value: "interested",
      label: hasUrl ? "Interested" : "Planning to apply",
      icon: ThumbsUp,
      activeClass: "bg-parchment border-studio-maroon text-studio-maroon",
    },
    {
      value: "applied",
      label: hasUrl ? "Applied externally" : "I've applied",
      icon: CheckCircle2,
      activeClass: "border-cohere-green text-cohere-green",
    },
    {
      value: "not_interested",
      label: "Not interested",
      icon: ThumbsDown,
      activeClass: "border-cohere-ink text-cohere-ink",
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
          {LEVELS.map(({ value, label, icon: Icon, activeClass }) => (
            <button
              key={value}
              onClick={() => handleSelect(value)}
              disabled={loading}
              className={`inline-flex items-center gap-1 rounded-full border bg-white px-2.5 py-1 text-[12px] transition-colors ${
                current === value
                  ? activeClass
                  : "border-hairline text-slate hover:border-cohere-ink hover:text-cohere-ink"
              }`}
            >
              {loading && current === value ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Icon className="h-3 w-3" />
              )}
              {label}
            </button>
          ))}
        </div>

        {error && <span className="text-[12px] text-error-red">{error}</span>}
      </div>

      {/* Soft nudge until they pick — quiet, useful, then gone */}
      {needsNudge && (
        <p className="text-micro text-slate-muted">
          Pick one — it sharpens what we show you next.
        </p>
      )}
    </div>
  );
}
