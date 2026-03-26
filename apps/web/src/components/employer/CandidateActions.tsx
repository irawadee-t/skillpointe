"use client";

/**
 * CandidateActions — client-side action buttons for an employer candidate card.
 * Includes "Reach out" (opens OutreachModal) and "Mark as hired" button.
 */
import { useState } from "react";
import { Mail, CheckCircle2, Loader2, MessageSquare } from "lucide-react";
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
    } catch {
      setHireError("Could not save. Please try again.");
    } finally {
      setHiring(false);
    }
  }

  return (
    <>
      <div className="flex items-center gap-2 mt-3 pt-3 border-t border-neutral-100">
        <button
          onClick={() => setShowOutreach(true)}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-neutral-700 border border-neutral-200 rounded-full px-3 py-1.5 hover:bg-neutral-50 transition-colors"
        >
          <Mail className="w-3.5 h-3.5" /> Reach out
        </button>

        <button
          onClick={handleMessage}
          disabled={startingDM}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-neutral-600 border border-neutral-200 rounded-full px-3 py-1.5 hover:bg-neutral-50 transition-colors disabled:opacity-50"
        >
          {startingDM ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <MessageSquare className="w-3.5 h-3.5" />
          )}
          {startingDM ? "Opening…" : "Message"}
        </button>

        {hired ? (
          <span className="inline-flex items-center gap-1 text-xs text-neutral-700 font-medium">
            <CheckCircle2 className="w-3.5 h-3.5" /> Marked as hired
          </span>
        ) : (
          <button
            onClick={handleHire}
            disabled={hiring}
            className="inline-flex items-center gap-1.5 text-xs text-neutral-500 border border-neutral-200 rounded-full px-3 py-1.5 hover:text-neutral-900 hover:border-neutral-400 transition-colors"
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
          <span className="text-xs text-red-600">{hireError}</span>
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
