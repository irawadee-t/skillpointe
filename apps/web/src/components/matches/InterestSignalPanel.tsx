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
  ExternalLink,
  ThumbsDown,
  ThumbsUp,
  Loader2,
  ClipboardList,
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
      activeClass: "bg-cyan-500/10 border-cyan-500 text-cyan-400",
    },
    {
      value: "applied",
      label: hasUrl ? "Applied externally" : "I've applied",
      icon: CheckCircle2,
      activeClass: "bg-emerald-500/10 border-emerald-500 text-emerald-400",
    },
    {
      value: "not_interested",
      label: "Not interested",
      icon: ThumbsDown,
      activeClass: "bg-zinc-800 border-zinc-600 text-zinc-400",
    },
  ];

  return (
    <div className="space-y-3">
      {/* Apply externally link — only shown when a URL exists */}
      {sourceUrl && (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-4 py-2 bg-cyan-500 text-black text-sm font-medium rounded-full hover:bg-cyan-400 transition-colors"
          onClick={() => {
            if (current !== "applied") handleSelect("applied");
          }}
        >
          <ExternalLink className="w-4 h-4" />
          Apply externally
        </a>
      )}

      {/* Self-reported status — always visible; more prominent when no URL */}
      <div>
        {!hasUrl && (
          <div className="flex items-center gap-1.5 mb-2 text-xs text-zinc-500">
            <ClipboardList className="w-3.5 h-3.5" />
            <span>Update your application status:</span>
          </div>
        )}
        {hasUrl && (
          <p className="text-xs text-zinc-500 mb-2">Your interest level:</p>
        )}

        <div className="flex flex-wrap gap-2">
          {LEVELS.map(({ value, label, icon: Icon, activeClass }) => (
            <button
              key={value}
              onClick={() => handleSelect(value)}
              disabled={loading}
              className={`inline-flex items-center gap-1.5 text-sm border rounded-full px-3 py-1.5 transition-all ${
                current === value
                  ? activeClass
                  : "border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
              }`}
            >
              {loading && current === value ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Icon className="w-3.5 h-3.5" />
              )}
              {label}
            </button>
          ))}
        </div>

        {current && (
          <p className="mt-1.5 text-xs text-zinc-500">
            Saved:{" "}
            <span className="font-medium text-zinc-300">
              {LEVELS.find((l) => l.value === current)?.label ?? current}
            </span>
          </p>
        )}

        {error && <p className="mt-1.5 text-xs text-rose-400">{error}</p>}
      </div>
    </div>
  );
}
