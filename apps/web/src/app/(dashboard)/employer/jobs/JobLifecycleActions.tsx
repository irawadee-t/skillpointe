"use client";

/**
 * JobLifecycleActions — per-row lifecycle management for the employer jobs
 * list: status chip + quick-actions menu (Pause / Resume / Mark as filled /
 * Close / Reopen / Delete).
 *
 * Contract behaviors:
 *  - Optimistic UI with REAL undo: every transition's toast Undo calls the
 *    revert endpoint (which restores previous_status server-side). If the
 *    revert fails we say so and roll the UI back — never a fake undo.
 *  - "Mark as filled" asks "Did you hire through SKILLED?" — yes links into
 *    the EXISTING hire flow (POST …/candidates/{id}/hire, the same endpoint
 *    the candidate list uses) before marking filled; no just marks filled.
 *  - Delete only for zero-activity jobs; jobs with history explain that
 *    Close is the honest action (analytics stay intact).
 *  - Chips come from the semantic statusTones slots — never hand-rolled.
 */
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Archive,
  CheckCircle2,
  Loader2,
  MoreHorizontal,
  Pause,
  Play,
  RotateCcw,
  Trash2,
} from "lucide-react";

import { ApiError } from "@/lib/api/client";
import { apiFetch } from "@/lib/api/client";
import {
  deleteJob,
  fetchJobApplicants,
  patchJobStatus,
  revertJobStatus,
  type ApplicantMatchSummary,
  type JobLifecycleStatus,
} from "@/lib/api/employer";
import { Dialog, useToast } from "@/components/ui";
import { statusChipClass, type StatusTone } from "@/components/ui/statusTones";

const STATUS_META: Record<JobLifecycleStatus, { label: string; tone: StatusTone }> = {
  active: { label: "Active", tone: "positive" },
  paused: { label: "Paused", tone: "muted" },
  filled: { label: "Filled", tone: "positiveSolid" },
  closed: { label: "Closed", tone: "muted" },
};

const TRANSITION_TOASTS: Record<JobLifecycleStatus, string> = {
  active: "Job reopened. Applicants can see it again",
  paused: "Job paused. Hidden from applicants until you resume",
  filled: "Job marked as filled",
  closed: "Job closed",
};

export function JobStatusChip({ status }: { status: JobLifecycleStatus }) {
  if (status === "active") return null; // active is the quiet default
  const meta = STATUS_META[status];
  return <span className={statusChipClass(meta.tone, "shrink-0")}>{meta.label}</span>;
}

export default function JobLifecycleActions({
  token, jobId, jobTitle, initialStatus, hasActivity,
}: {
  token: string;
  jobId: string;
  jobTitle: string;
  initialStatus: JobLifecycleStatus;
  hasActivity: boolean;
}) {
  const router = useRouter();
  const toast = useToast();
  const [status, setStatus] = useState<JobLifecycleStatus>(initialStatus);
  const [busy, setBusy] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirming, setConfirming] = useState<"close" | "delete" | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  // Fill dialog state
  const [fillOpen, setFillOpen] = useState(false);
  const [fillStep, setFillStep] = useState<"ask" | "pick">("ask");
  const [candidates, setCandidates] = useState<ApplicantMatchSummary[] | null>(null);
  const [hiringId, setHiringId] = useState<string | null>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onDown(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
        setConfirming(null);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menuOpen]);

  function fail(e: unknown, fallback: string) {
    if (e instanceof ApiError) {
      try {
        const detail = JSON.parse(e.message)?.detail;
        if (typeof detail === "string") { toast.error(detail); return; }
      } catch { /* not JSON */ }
    }
    toast.error(fallback);
  }

  /** Optimistic transition with a REAL undo (revert endpoint) in the toast. */
  async function transition(to: JobLifecycleStatus, message?: string) {
    const prev = status;
    setStatus(to);
    setMenuOpen(false);
    setConfirming(null);
    setBusy(true);
    try {
      await patchJobStatus(token, jobId, to);
      toast.undo(message ?? TRANSITION_TOASTS[to], async () => {
        setStatus(prev);
        try {
          await revertJobStatus(token, jobId);
          router.refresh();
        } catch {
          setStatus(to);
          toast.error("Couldn't undo. Refresh to see the current state.");
        }
      });
      router.refresh();
    } catch (e) {
      setStatus(prev);
      fail(e, "Couldn't update the job. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    setMenuOpen(false);
    setConfirming(null);
    setBusy(true);
    try {
      await deleteJob(token, jobId);
      toast.success("Posting deleted");
      router.refresh();
    } catch (e) {
      fail(e, "Couldn't delete this posting.");
    } finally {
      setBusy(false);
    }
  }

  async function openFillDialog() {
    setMenuOpen(false);
    setFillStep("ask");
    setFillOpen(true);
  }

  async function loadCandidates() {
    setFillStep("pick");
    if (candidates !== null) return;
    try {
      const res = await fetchJobApplicants(jobId, token, { perPage: 10 });
      setCandidates(res.applicants);
    } catch {
      setCandidates([]);
    }
  }

  /** Yes-path: record the hire through the EXISTING hire flow, then fill. */
  async function hireAndFill(candidate: ApplicantMatchSummary) {
    const name = [candidate.first_name, candidate.last_name].filter(Boolean).join(" ")
      || "candidate";
    setHiringId(candidate.applicant_id);
    try {
      await apiFetch(
        `/employer/me/jobs/${jobId}/candidates/${candidate.applicant_id}/hire`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            outcome_type: "hired",
            hire_date: new Date().toISOString().slice(0, 10),
          }),
        },
      );
      setFillOpen(false);
      await transition("filled", `Hire recorded: ${name} · job marked as filled`);
    } catch (e) {
      fail(e, "Couldn't record the hire. Please try again.");
    } finally {
      setHiringId(null);
    }
  }

  const itemCls =
    "flex w-full items-center gap-2 px-3 py-2 text-left text-body text-cohere-ink " +
    "hover:bg-stone/40 transition-colors duration-200 disabled:opacity-50";

  return (
    <div className="flex items-center gap-2">
      <JobStatusChip status={status} />
      <div className="relative" ref={menuRef}>
        <button
          type="button"
          aria-label={`Manage ${jobTitle}`}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => { setMenuOpen((v) => !v); setConfirming(null); }}
          disabled={busy}
          className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-hairline bg-white text-slate hover:text-cohere-ink hover:shadow-float transition-[color,box-shadow] duration-200 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <MoreHorizontal className="w-4 h-4" />}
        </button>

        {menuOpen && (
          <div
            role="menu"
            className="absolute right-0 top-9 z-20 w-64 overflow-hidden rounded-[10px] border border-hairline bg-white py-1 shadow-float"
          >
            {status === "active" && (
              <button role="menuitem" className={itemCls} onClick={() => transition("paused")}>
                <Pause className="w-4 h-4 text-slate" /> Pause posting
              </button>
            )}
            {status === "paused" && (
              <button role="menuitem" className={itemCls} onClick={() => transition("active")}>
                <Play className="w-4 h-4 text-slate" /> Resume posting
              </button>
            )}
            {(status === "active" || status === "paused") && (
              <button role="menuitem" className={itemCls} onClick={openFillDialog}>
                <CheckCircle2 className="w-4 h-4 text-slate" /> Mark as filled
              </button>
            )}
            {(status === "filled" || status === "closed") && (
              <button role="menuitem" className={itemCls} onClick={() => transition("active")}>
                <RotateCcw className="w-4 h-4 text-slate" /> Reopen posting
              </button>
            )}
            {(status === "active" || status === "paused") && (
              confirming === "close" ? (
                <div className="px-3 py-2">
                  <p className="text-body text-cohere-ink">Close this job?</p>
                  <p className="text-micro text-slate-muted mt-0.5">
                    Applicants stop seeing it. You can reopen later.
                  </p>
                  <div className="mt-2 flex gap-2">
                    <button className="btn-primary !py-1 !px-3 text-[13px]" onClick={() => transition("closed")}>
                      Close job
                    </button>
                    <button
                      className="text-body text-slate hover:text-cohere-ink transition-colors"
                      onClick={() => setConfirming(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button role="menuitem" className={itemCls} onClick={() => setConfirming("close")}>
                  <Archive className="w-4 h-4 text-slate" /> Close posting
                </button>
              )
            )}

            <div className="my-1 border-t border-hairline" />
            {hasActivity ? (
              <div className="px-3 py-2">
                <p className="flex items-center gap-2 text-body text-slate-muted">
                  <Trash2 className="w-4 h-4" /> Delete
                </p>
                <p className="text-micro text-slate-muted mt-0.5">
                  This job has candidate activity, so its record stays. Close
                  it instead.
                </p>
              </div>
            ) : confirming === "delete" ? (
              <div className="px-3 py-2">
                <p className="text-body text-cohere-ink">Delete this posting for good?</p>
                <div className="mt-2 flex gap-2">
                  <button
                    className="rounded-full bg-error-red px-3 py-1 text-[13px] font-medium text-white hover:opacity-90 transition-opacity"
                    onClick={handleDelete}
                  >
                    Delete
                  </button>
                  <button
                    className="text-body text-slate hover:text-cohere-ink transition-colors"
                    onClick={() => setConfirming(null)}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button role="menuitem" className={itemCls} onClick={() => setConfirming("delete")}>
                <Trash2 className="w-4 h-4 text-slate" /> Delete
              </button>
            )}
          </div>
        )}
      </div>

      {/* Mark-as-filled: link the hire into the existing hire flow when it
          happened through SKILLED; otherwise just mark filled. */}
      <Dialog open={fillOpen} onClose={() => setFillOpen(false)} title={`Mark “${jobTitle}” as filled`}>
        {fillStep === "ask" ? (
          <div>
            <p className="text-body text-slate">
              Did you hire through SKILLED? Recording the hire keeps your
              analytics and the candidate&apos;s record accurate.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn-primary" onClick={loadCandidates}>
                Yes, pick the candidate
              </button>
              <button
                className="btn-secondary"
                onClick={() => { setFillOpen(false); transition("filled"); }}
              >
                No, just mark as filled
              </button>
            </div>
          </div>
        ) : (
          <div>
            <p className="text-body text-slate">Who did you hire?</p>
            <div className="mt-3 max-h-72 overflow-y-auto rounded-[10px] border border-hairline">
              {candidates === null ? (
                <p className="flex items-center gap-2 px-4 py-3 text-body text-slate">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading candidates…
                </p>
              ) : candidates.length === 0 ? (
                <p className="px-4 py-3 text-body text-slate">
                  No ranked candidates for this job yet.
                </p>
              ) : (
                candidates.map((c) => {
                  const name = [c.first_name, c.last_name].filter(Boolean).join(" ")
                    || "Unnamed candidate";
                  const where = [c.city, c.state].filter(Boolean).join(", ");
                  return (
                    <button
                      key={c.applicant_id}
                      className="flex w-full items-center justify-between gap-3 border-t border-hairline px-4 py-2.5 text-left first:border-t-0 hover:bg-stone/40 transition-colors"
                      onClick={() => hireAndFill(c)}
                      disabled={hiringId !== null}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-body font-medium text-cohere-ink">{name}</span>
                        {where && <span className="block text-micro text-slate-muted">{where}</span>}
                      </span>
                      {hiringId === c.applicant_id
                        ? <Loader2 className="w-4 h-4 animate-spin text-slate" />
                        : <span className="text-micro font-medium text-cohere-blue shrink-0">Record hire</span>}
                    </button>
                  );
                })
              )}
            </div>
            <div className="mt-3 flex justify-between">
              <button
                className="text-body text-slate hover:text-cohere-ink transition-colors"
                onClick={() => setFillStep("ask")}
              >
                Back
              </button>
              <button
                className="text-body text-slate hover:text-cohere-ink transition-colors"
                onClick={() => { setFillOpen(false); transition("filled"); }}
              >
                Skip and mark filled without recording
              </button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}
