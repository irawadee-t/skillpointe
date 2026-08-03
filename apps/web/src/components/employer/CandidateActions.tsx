"use client";

/**
 * CandidateActions — client-side action buttons for an employer candidate card.
 * Includes "Reach out" (opens OutreachModal) and "Mark as hired" button.
 */
import { useEffect, useState } from "react";
import { Mail, CheckCircle2, Loader2, MessageSquare, History } from "lucide-react";
import { OutreachModal } from "./OutreachModal";
import { useRouter } from "next/navigation";
import { useToast } from "@/components/ui";
import { formatDateShort } from "@/lib/format";

interface CandidateActionsProps {
  matchId: string;
  applicantId: string;
  jobId: string;
  applicantName: string;
  jobTitle: string;
  token: string;
}

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

export function CandidateActions({
  matchId,
  applicantId,
  jobId,
  applicantName,
  jobTitle,
  token,
}: CandidateActionsProps) {
  const router = useRouter();
  const toast = useToast();
  const [showOutreach, setShowOutreach] = useState(false);
  const [hiring, setHiring] = useState(false);
  const [hired, setHired] = useState(false);
  const [confirmingHire, setConfirmingHire] = useState(false);
  const [hireError, setHireError] = useState<string | null>(null);
  const [startingDM, setStartingDM] = useState(false);
  const [priorOutreachAt, setPriorOutreachAt] = useState<string | null>(null);
  // Optional annual wage, reported at hire time — feeds Foundation outcome
  // analytics (median placement wage). Left blank = not reported.
  const [hireWage, setHireWage] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const url = `${API_URL}/employer/me/outreach/history?applicant_id=${encodeURIComponent(applicantId)}&job_id=${encodeURIComponent(jobId)}`;
        const res = await fetch(url, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) return;
        const data: { items?: Array<{ sent_at: string | null }> } = await res.json();
        if (cancelled) return;
        const latest = data.items?.[0]?.sent_at ?? null;
        setPriorOutreachAt(latest);
      } catch {
        // Best effort — history is a nice-to-have.
      }
    })();
    return () => { cancelled = true; };
  }, [applicantId, jobId, token, showOutreach]);

  async function handleMessage() {
    setStartingDM(true);
    try {
      const res = await fetch(`${API_URL}/conversations`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ applicant_id: applicantId, job_id: jobId }),
      });
      if (!res.ok) throw new Error("Failed");
      const data = await res.json();
      router.push(`/employer/messages/${data.conversation_id}`);
    } catch {
      toast.error("Could not open conversation. Please try again.");
    } finally {
      setStartingDM(false);
    }
  }

  async function handleHire() {
    setHiring(true);
    setHireError(null);
    try {
      const res = await fetch(
        `${API_URL}/employer/me/jobs/${jobId}/candidates/${applicantId}/hire`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            outcome_type: "hired",
            match_id: matchId,
            reported_wage_annual: /^\d{4,7}$/.test(hireWage.trim())
              ? Number(hireWage.trim())
              : null,
          }),
        }
      );
      if (!res.ok) throw new Error("Failed");
      setHired(true);
      // Refresh server components so dashboard eligible/near-fit counts update.
      router.refresh();
    } catch {
      setHireError("Could not save. Please try again.");
    } finally {
      setHiring(false);
    }
  }

  return (
    <>
      <div className="mt-4 pt-4 border-t border-hairline">
        {/* All action buttons share ONE baseline row — the prior-outreach
            caption renders on its own line below so it can never push a
            button out of alignment. */}
        <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setShowOutreach(true)}
          className="btn-pill-outline text-micro"
        >
          <Mail className="w-3.5 h-3.5" /> {priorOutreachAt ? "Reach out again" : "Reach out"}
        </button>

        <button
          onClick={handleMessage}
          disabled={startingDM}
          className="btn-pill-outline text-micro disabled:opacity-50"
        >
          {startingDM ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <MessageSquare className="w-3.5 h-3.5" />
          )}
          {startingDM ? "Opening…" : "Message"}
        </button>

        {hired ? (
          <span className="inline-flex items-center gap-1 text-micro text-cohere-green font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" /> Marked as hired
          </span>
        ) : confirmingHire ? (
          <span className="inline-flex flex-wrap items-center gap-2">
            <span className="text-micro text-slate">
              Mark {applicantName} as hired for {jobTitle}?
            </span>
            <input
              type="text"
              inputMode="numeric"
              value={hireWage}
              onChange={(e) => setHireWage(e.target.value)}
              placeholder="Annual wage (optional)"
              aria-label="Annual wage in dollars (optional)"
              className="input-cohere w-40 px-2 py-1 text-micro"
              disabled={hiring}
            />
            <button
              onClick={handleHire}
              disabled={hiring}
              className="inline-flex items-center gap-1 rounded-pill bg-cohere-green px-3 py-1.5 text-micro font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {hiring ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
              {hiring ? "Saving…" : "Confirm"}
            </button>
            <button
              onClick={() => setConfirmingHire(false)}
              disabled={hiring}
              className="text-micro text-slate hover:text-ink"
            >
              Cancel
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirmingHire(true)}
            className="btn-pill-outline text-micro hover:text-cohere-green hover:border-cohere-green/40"
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            Mark as hired
          </button>
        )}

        {hireError && (
          <span className="text-micro text-error-red">{hireError}</span>
        )}
        </div>

        {priorOutreachAt && (
          <p className="mt-1.5 flex items-center gap-1 text-micro text-slate-muted">
            <History className="w-3 h-3" />
            Previously reached out {formatDateShort(priorOutreachAt)}
          </p>
        )}
      </div>

      {showOutreach && (
        <OutreachModal
          matchId={matchId}
          applicantId={applicantId}
          jobId={jobId}
          applicantName={applicantName}
          jobTitle={jobTitle}
          token={token}
          onClose={() => setShowOutreach(false)}
        />
      )}
    </>
  );
}
