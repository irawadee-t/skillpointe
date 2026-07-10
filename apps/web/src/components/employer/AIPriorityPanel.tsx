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
    <div className="card-green overflow-hidden">
      {/* Toggle header */}
      <button
        onClick={loadPriorities}
        disabled={loading}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/5 transition-colors"
      >
        <span className="flex items-center gap-2 text-body-lg font-semibold text-white">
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4" />
          )}
          {loading ? "Analysing candidates…" : "AI Candidate Prioritisation"}
        </span>
        <span className="text-white/70">
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
            <div className="border-t border-white/15 px-5 pb-5 pt-4 space-y-3">
              {!generated && (
                <div className="mb-2 flex items-start gap-2 rounded-md border border-amber-400/60 bg-amber-50 px-3 py-2.5 text-caption text-amber-900">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                  <div>
                    <p className="font-medium">AI ranking is offline — showing raw score ranking.</p>
                    <p className="mt-0.5 text-micro text-amber-800">
                      Ask admin to configure <code>OPENAI_API_KEY</code>.
                    </p>
                  </div>
                </div>
              )}
              {priorities.length === 0 ? (
                <p className="text-body text-white/80">No matched candidates to prioritize.</p>
              ) : (
                priorities.map((c, i) => (
                  <motion.div
                    key={c.applicant_id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, ease: easeCohere, delay: i * 0.04 }}
                    className="bg-white rounded-md px-4 py-4 border border-border-light"
                  >
                    {/* Rank + name row */}
                    <div className="flex items-start gap-3">
                      <div className="shrink-0 w-6 h-6 rounded-full bg-cohere-green text-white text-micro font-bold flex items-center justify-center mt-0.5 tabular-nums">
                        {i + 1}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-body font-semibold text-cohere-ink">{c.name}</span>
                          {c.score !== null && (
                            <span className="text-caption font-medium text-cohere-green tabular-nums">
                              {Math.round(c.score)}/100
                            </span>
                          )}
                          {i === 0 && (
                            <span className="inline-flex items-center gap-0.5 text-micro text-studio-maroon bg-studio-maroon/10 border border-studio-maroon-soft rounded-sm px-1.5 py-0.5">
                              Top pick
                            </span>
                          )}
                          <span
                            className={`text-micro rounded-sm px-1.5 py-0.5 border ${
                              c.eligibility_status === "eligible"
                                ? "text-cohere-green bg-wash-green border-cohere-green/20"
                                : "text-studio-maroon bg-studio-maroon/10 border-studio-maroon-soft"
                            }`}
                          >
                            {c.eligibility_status === "eligible" ? "Eligible" : "Near fit"}
                          </span>
                        </div>
                        <p className="text-body text-slate mt-1 leading-snug">{c.reason}</p>
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
