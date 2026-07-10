"use client";

/**
 * CandidateActions — client-side action buttons for an employer candidate card.
 * Includes "Reach out" (opens OutreachModal) and "Mark as hired" button.
 */
import { useEffect, useState } from "react";
import { Mail, CheckCircle2, Loader2, MessageSquare, History } from "lucide-react";
import { OutreachModal } from "./OutreachModal";
import { useRouter } from "next/navigation";

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
  const [showOutreach, setShowOutreach] = useState(false);
  const [hiring, setHiring] = useState(false);
  const [hired, setHired] = useState(false);
  const [hireError, setHireError] = useState<string | null>(null);
  const [startingDM, setStartingDM] = useState(false);
  const [priorOutreachAt, setPriorOutreachAt] = useState<string | null>(null);

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
      alert("Could not open conversation. Please try again.");
    } finally {
      setStartingDM(false);
    }
  }

  async function handleHire() {
    if (!confirm(`Mark ${applicantName} as hired for ${jobTitle}?`)) return;
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
          body: JSON.stringify({ outcome_type: "hired", match_id: matchId }),
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
      <div className="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t border-hairline">
        <div className="flex flex-col items-start">
          <button
            onClick={() => setShowOutreach(true)}
            className="btn-pill-outline text-micro"
          >
            <Mail className="w-3.5 h-3.5" /> {priorOutreachAt ? "Reach out again" : "Reach out"}
          </button>
          {priorOutreachAt && (
            <span className="mt-1 inline-flex items-center gap-1 text-micro text-slate-muted">
              <History className="w-3 h-3" />
              Previously reached out {new Date(priorOutreachAt).toLocaleDateString()}
            </span>
          )}
        </div>

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
        ) : (
          <button
            onClick={handleHire}
            disabled={hiring}
            className="btn-pill-outline text-micro hover:text-cohere-green hover:border-cohere-green/40"
          >
            {hiring ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <CheckCircle2 className="w-3.5 h-3.5" />
            )}
            {hiring ? "Saving…" : "Mark as hired"}
          </button>
        )}

        {hireError && (
          <span className="text-micro text-error-red">{hireError}</span>
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
