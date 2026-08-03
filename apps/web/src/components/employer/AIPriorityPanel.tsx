"use client";

/**
 * AIPriorityPanel — shows AI-ranked candidates with reasoning.
 *
 * Lazy-loads when the employer clicks "Prioritize with AI". Shows a
 * ranked list with a 1-sentence reason per candidate and action buttons
 * (Reach out, Message, Mark as hired) for each row.
 */

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Sparkles, Loader2, ChevronDown, ChevronUp, AlertTriangle } from "lucide-react";
import { easeCohere } from "@/lib/motion";
import { CandidateActions } from "./CandidateActions";
import { EligibilityBadge } from "@/components/matches/MatchLabel";

interface PriorityCandidate {
  match_id: string;
  applicant_id: string;
  name: string;
  score: number | null;
  eligibility_status: string;
  reason: string;
}

interface Props {
  jobId: string;
  jobTitle: string;
  token: string;
  isAdmin?: boolean;
}

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

export function AIPriorityPanel({ jobId, jobTitle, token, isAdmin = false }: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [priorities, setPriorities] = useState<PriorityCandidate[] | null>(null);
  const [generated, setGenerated] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadPriorities() {
    if (priorities !== null) {
      setOpen((o) => !o);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/employer/me/jobs/${jobId}/applicants/ai-priority`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) throw new Error("Failed");
      const data = await res.json();
      setPriorities(data.priorities ?? []);
      setGenerated(data.generated ?? false);
      setOpen(true);
    } catch {
      setError("Could not load AI priorities. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-[10px] border border-hairline bg-white overflow-hidden">
      {/* Toggle header */}
      <button
        onClick={loadPriorities}
        disabled={loading}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-stone/40 transition-colors"
      >
        <span className="flex items-center gap-2 text-body-lg font-semibold text-cohere-ink">
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4" />
          )}
          {loading ? "Analyzing candidates…" : "AI candidate prioritization"}
        </span>
        <span className="text-slate">
          {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </span>
      </button>

      {/* Results */}
      <AnimatePresence initial={false}>
        {open && priorities !== null && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: easeCohere }}
            className="overflow-hidden"
          >
            <div className="border-t border-hairline">
              {!generated && (
                // No internal config jargon here — the server logs the cause.
                <div className="mx-5 mt-4 flex items-start gap-2 rounded-md border border-amber-400/60 bg-amber-50 px-3 py-2.5 text-caption text-amber-900">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                  <p className="font-medium">AI ranking is temporarily unavailable. Showing score order.</p>
                </div>
              )}
              {priorities.length === 0 ? (
                <p className="px-5 py-4 text-body text-slate">No matched candidates to prioritize.</p>
              ) : (
                priorities.map((c, i) => (
                  <motion.div
                    key={c.applicant_id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, ease: easeCohere, delay: i * 0.04 }}
                    className={`px-5 py-3.5 ${i > 0 ? "border-t border-hairline" : ""}`}
                  >
                    {/* Rank + name row */}
                    <div className="flex items-start gap-3">
                      <span className="shrink-0 mt-0.5 text-body text-slate-muted tabular-nums">
                        {i + 1}.
                      </span>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-body font-semibold text-cohere-ink">{c.name}</span>
                          {c.score !== null && (
                            <span className="text-caption font-medium text-cohere-green tabular-nums">
                              {/* Floor — same convention as both match-card
                                  surfaces, so one stored score never shows
                                  two different numbers. */}
                              {Math.min(99, Math.floor(c.score))}/100
                            </span>
                          )}
                          {i === 0 && (
                            // Emphasis, not a status — solid ink so it can't be
                            // confused with the maroon attention slot beside it.
                            <span className="inline-flex items-center gap-0.5 rounded-full border border-cohere-ink bg-ink px-2 py-0.5 text-[11px] font-medium text-white">
                              Top pick
                            </span>
                          )}
                          <EligibilityBadge status={c.eligibility_status ?? ""} />
                        </div>
                        {/* Empty reason = nothing candidate-specific to say —
                            show no line rather than repeated boilerplate. */}
                        {c.reason && <p className="text-body text-slate mt-1 leading-snug">{c.reason}</p>}
                      </div>
                    </div>

                    {/* Action buttons — hidden for admin */}
                    {!isAdmin && (
                      <CandidateActions
                        matchId={c.match_id}
                        applicantId={c.applicant_id}
                        jobId={jobId}
                        applicantName={c.name}
                        jobTitle={jobTitle}
                        token={token}
                      />
                    )}
                  </motion.div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {error && (
        <p className="text-caption text-error-red px-5 pb-4">{error}</p>
      )}
    </div>
  );
}
