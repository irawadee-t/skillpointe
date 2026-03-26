"use client";

/**
 * AIPriorityPanel — shows AI-ranked candidates with reasoning.
 *
 * Lazy-loads when the employer clicks "Prioritize with AI". Shows a
 * ranked list with a 1-sentence reason per candidate and action buttons
 * (Reach out, Message, Mark as hired) for each row.
 */

import { useState } from "react";
import { Sparkles, Loader2, Star, ChevronDown, ChevronUp } from "lucide-react";
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
    <div className="bg-gradient-to-r from-spf-navy/5 to-purple-50 border border-spf-navy/20 rounded-xl overflow-hidden">
      {/* Toggle header */}
      <button
        onClick={loadPriorities}
        disabled={loading}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-spf-navy/5 transition-colors"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-spf-navy">
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4" />
          )}
          {loading ? "Analysing candidates…" : "AI Candidate Prioritisation"}
        </span>
        <span className="text-xs text-spf-navy/60">
          {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </span>
      </button>

      {/* Results */}
      {open && priorities !== null && (
        <div className="border-t border-spf-navy/10 px-4 pb-4 pt-3 space-y-3">
          {!generated && (
            <p className="text-xs text-gray-500 italic mb-2">
              AI key not configured — showing score-based order only.
            </p>
          )}
          {priorities.length === 0 ? (
            <p className="text-sm text-gray-500">No matched candidates to prioritise.</p>
          ) : (
            priorities.map((c, i) => (
              <div
                key={c.applicant_id}
                className="bg-white rounded-lg px-3 py-3 border border-gray-100"
              >
                {/* Rank + name row */}
                <div className="flex items-start gap-3">
                  <div className="shrink-0 w-6 h-6 rounded-full bg-spf-navy text-white text-xs font-bold flex items-center justify-center mt-0.5">
                    {i + 1}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-gray-900">{c.name}</span>
                      {c.score !== null && (
                        <span className="text-xs text-gray-500 tabular-nums">
                          {Math.round(c.score)}/100
                        </span>
                      )}
                      {i === 0 && (
                        <span className="inline-flex items-center gap-0.5 text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 rounded px-1.5 py-0.5">
                          <Star className="w-2.5 h-2.5" /> Top pick
                        </span>
                      )}
                      <span
                        className={`text-xs rounded px-1.5 py-0.5 border ${
                          c.eligibility_status === "eligible"
                            ? "text-green-700 bg-green-50 border-green-200"
                            : "text-orange-600 bg-orange-50 border-orange-200"
                        }`}
                      >
                        {c.eligibility_status === "eligible" ? "Eligible" : "Near fit"}
                      </span>
                    </div>
                    <p className="text-xs text-gray-600 mt-0.5 leading-snug">{c.reason}</p>
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
              </div>
            ))
          )}
        </div>
      )}

      {error && (
        <p className="text-xs text-red-600 px-4 pb-3">{error}</p>
      )}
    </div>
  );
}
