"use client";

/**
 * ChatJobPicker — modal for choosing a job before starting a planning chat.
 *
 * Three sections:
 *   1. Eligible matches  (best immediate opportunities)
 *   2. Near-fit matches  (promising)
 *   3. Browse all jobs   (text search against /jobs/browse)
 *
 * After selection the component POSTs to create a job-focused session
 * and navigates to it. The session will contain an AI-generated opening
 * message summarising the selected job's gaps, strengths, and next steps.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Plus,
  Loader2,
  X,
  Search,
  ChevronRight,
  Star,
  TrendingUp,
} from "lucide-react";

interface Props {
  token: string;
}

interface MatchItem {
  match_id: string;
  job_id: string;
  job_title: string;
  employer_name: string;
  score: number | null;
  status: "eligible" | "near_fit";
}

interface BrowseItem {
  job_id: string;
  title: string;
  employer_name: string;
  state: string | null;
}

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

export function ChatJobPicker({ token }: Props) {
  const router = useRouter();

  const [open, setOpen] = useState(false);
  const [startingJobId, setStartingJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"matches" | "browse">("matches");

  // Matches tab state
  const [matchesLoading, setMatchesLoading] = useState(false);
  const [eligible, setEligible] = useState<MatchItem[]>([]);
  const [nearFit, setNearFit] = useState<MatchItem[]>([]);

  // Browse tab state
  const [searchQ, setSearchQ] = useState("");
  const [browseResults, setBrowseResults] = useState<BrowseItem[]>([]);
  const [browseLoading, setBrowseLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load matches when modal opens
  useEffect(() => {
    if (!open) return;
    setMatchesLoading(true);
    fetch(`${API_URL}/applicant/me/matches`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => {
        const toItem = (m: Record<string, unknown>, s: "eligible" | "near_fit"): MatchItem => ({
          match_id: String(m.match_id ?? ""),
          job_id: String(m.job_id ?? ""),
          job_title: String(m.job_title ?? m.title_normalized ?? m.title_raw ?? "Untitled"),
          employer_name: String(m.employer_name ?? ""),
          score:
            m.policy_adjusted_score != null
              ? parseFloat(String(m.policy_adjusted_score))
              : null,
          status: s,
        });
        setEligible((data.eligible_matches ?? []).map((m: Record<string, unknown>) => toItem(m, "eligible")));
        setNearFit((data.near_fit_matches ?? []).map((m: Record<string, unknown>) => toItem(m, "near_fit")));
      })
      .catch(() => {
        setEligible([]);
        setNearFit([]);
      })
      .finally(() => setMatchesLoading(false));
  }, [open, token]);

  // Debounced browse search
  const runBrowse = useCallback(
    (q: string) => {
      setBrowseLoading(true);
      fetch(`${API_URL}/jobs/browse?q=${encodeURIComponent(q)}&per_page=12`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then((data) =>
          setBrowseResults(
            (data.jobs ?? []).map((j: Record<string, unknown>) => ({
              job_id: String(j.job_id ?? ""),
              title: String(j.title ?? ""),
              employer_name: String(j.employer_name ?? ""),
              state: j.state ? String(j.state) : null,
            }))
          )
        )
        .catch(() => setBrowseResults([]))
        .finally(() => setBrowseLoading(false));
    },
    [token]
  );

  useEffect(() => {
    if (activeTab !== "browse") return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runBrowse(searchQ), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchQ, activeTab, runBrowse]);

  // Trigger initial browse load when tab activates
  useEffect(() => {
    if (activeTab === "browse" && browseResults.length === 0 && !browseLoading) {
      runBrowse("");
    }
    // intentionally only run when tab changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  async function startChat(jobId: string) {
    setStartingJobId(jobId);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/applicant/me/chat/sessions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ job_id: jobId }),
      });
      if (!res.ok) throw new Error("Failed");
      const data = await res.json();
      setOpen(false);
      router.push(`/applicant/chat/${data.session_id}`);
    } catch {
      setError("Could not start chat. Please try again.");
    } finally {
      setStartingJobId(null);
    }
  }

  function handleOpen() {
    setOpen(true);
    setError(null);
    setActiveTab("matches");
    setSearchQ("");
  }

  return (
    <>
      <button
        onClick={handleOpen}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-white bg-neutral-900 rounded-full px-3 py-1.5 hover:bg-neutral-700 transition-colors"
      >
        <Plus className="w-4 h-4" />
        New chat
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={(e) => {
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div className="bg-white rounded-xl border border-neutral-200 w-full max-w-lg flex flex-col max-h-[80vh]">
            {/* Header */}
            <div className="flex items-start justify-between px-5 pt-5 pb-4 border-b border-neutral-100 shrink-0">
              <div>
                <h2 className="font-semibold text-neutral-900 text-base">
                  Choose a job to discuss
                </h2>
                <p className="text-xs text-neutral-500 mt-0.5">
                  Pick a role and I&apos;ll open with your gaps, strengths, and
                  next steps
                </p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="p-1 rounded-lg hover:bg-neutral-100 text-neutral-400 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-neutral-100 px-5 shrink-0">
              {(["matches", "browse"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`text-sm font-medium py-2.5 mr-5 border-b-2 transition-colors ${
                    activeTab === tab
                      ? "border-neutral-900 text-neutral-900"
                      : "border-transparent text-neutral-500 hover:text-neutral-700"
                  }`}
                >
                  {tab === "matches" ? "Your matches" : "Browse all jobs"}
                </button>
              ))}
            </div>

            {/* Scrollable content */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
              {/* ── Matches tab ── */}
              {activeTab === "matches" && (
                <>
                  {matchesLoading ? (
                    <div className="flex justify-center py-10">
                      <Loader2 className="w-5 h-5 animate-spin text-neutral-400" />
                    </div>
                  ) : (
                    <>
                      {eligible.length > 0 && (
                        <section className="mb-3">
                          <p className="text-xs font-semibold text-neutral-500 uppercase tracking-wide mb-1.5 flex items-center gap-1 px-1">
                            <Star className="w-3 h-3" /> Eligible
                          </p>
                          {eligible.map((m) => (
                            <JobRow
                              key={m.job_id}
                              jobId={m.job_id}
                              title={m.job_title}
                              sub={m.employer_name}
                              score={m.score}
                              loading={startingJobId === m.job_id}
                              onSelect={startChat}
                            />
                          ))}
                        </section>
                      )}

                      {nearFit.length > 0 && (
                        <section className="mb-1">
                          <p className="text-xs font-semibold text-neutral-400 uppercase tracking-wide mb-1.5 flex items-center gap-1 px-1">
                            <TrendingUp className="w-3 h-3" /> Near fit
                          </p>
                          {nearFit.map((m) => (
                            <JobRow
                              key={m.job_id}
                              jobId={m.job_id}
                              title={m.job_title}
                              sub={m.employer_name}
                              score={m.score}
                              loading={startingJobId === m.job_id}
                              onSelect={startChat}
                            />
                          ))}
                        </section>
                      )}

                      {eligible.length === 0 && nearFit.length === 0 && (
                        <div className="py-10 text-center">
                          <p className="text-sm text-neutral-500">
                            No matches yet. Try browsing all jobs.
                          </p>
                        </div>
                      )}
                    </>
                  )}
                </>
              )}

              {/* ── Browse tab ── */}
              {activeTab === "browse" && (
                <>
                  <div className="relative mb-3">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-400 pointer-events-none" />
                    <input
                      type="text"
                      value={searchQ}
                      onChange={(e) => setSearchQ(e.target.value)}
                      placeholder="Search job title…"
                      className="w-full pl-9 pr-4 py-2 text-sm border border-neutral-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-neutral-400"
                      autoFocus
                    />
                  </div>

                  {browseLoading ? (
                    <div className="flex justify-center py-6">
                      <Loader2 className="w-5 h-5 animate-spin text-neutral-400" />
                    </div>
                  ) : browseResults.length > 0 ? (
                    browseResults.map((j) => (
                      <JobRow
                        key={j.job_id}
                        jobId={j.job_id}
                        title={j.title}
                        sub={[j.employer_name, j.state].filter(Boolean).join(" · ")}
                        score={null}
                        loading={startingJobId === j.job_id}
                        onSelect={startChat}
                      />
                    ))
                  ) : (
                    <p className="text-sm text-neutral-400 text-center py-6">
                      {searchQ
                        ? "No jobs match your search."
                        : "No jobs available."}
                    </p>
                  )}
                </>
              )}
            </div>

            {/* Error footer */}
            {error && (
              <div className="px-5 pb-4 shrink-0">
                <p className="text-xs text-red-600">{error}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// JobRow sub-component
// ---------------------------------------------------------------------------

interface JobRowProps {
  jobId: string;
  title: string;
  sub: string;
  score: number | null;
  loading: boolean;
  onSelect: (jobId: string) => void;
}

function JobRow({ jobId, title, sub, score, loading, onSelect }: JobRowProps) {
  return (
    <button
      onClick={() => onSelect(jobId)}
      disabled={loading}
      className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-neutral-50 text-left group transition-colors disabled:opacity-50"
    >
      <div className="min-w-0">
        <p className="text-sm font-medium text-neutral-900 truncate">{title}</p>
        {sub && <p className="text-xs text-neutral-500 truncate">{sub}</p>}
      </div>
      <div className="flex items-center gap-2 ml-3 shrink-0">
        {score !== null && (
          <span className="text-xs font-semibold text-neutral-500 tabular-nums">
            {Math.round(score)}
          </span>
        )}
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin text-neutral-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-neutral-300 group-hover:text-neutral-500 transition-colors" />
        )}
      </div>
    </button>
  );
}
