"use client";

/**
 * OutreachModal — employer reach-out dialog for a matched candidate.
 *
 * Allows the employer to:
 *  1. Request an AI-generated draft
 *  2. Edit the draft manually
 *  3. Mark as sent (records in employer_outreach table)
 */
import { useState } from "react";
import { motion } from "motion/react";
import { X, Sparkles, Loader2, Send, CheckCircle2 } from "lucide-react";
import { easeCohere } from "@/lib/motion";
import { useToast } from "@/components/ui";

interface OutreachModalProps {
  matchId: string;
  applicantId: string;
  jobId: string;
  applicantName: string;
  jobTitle: string;
  token: string;
  onClose: () => void;
}

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

export function OutreachModal({
  matchId,
  applicantId,
  jobId,
  applicantName,
  jobTitle,
  token,
  onClose,
}: OutreachModalProps) {
  const toast = useToast();
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [aiGenerated, setAiGenerated] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [, setSentOutreachId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleDraft() {
    setDrafting(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/employer/me/outreach/draft`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ match_id: matchId, applicant_id: applicantId, job_id: jobId }),
      });
      if (!res.ok) throw new Error("Draft failed");
      const data = await res.json();
      setSubject(data.subject ?? "");
      setBody(data.body ?? "");
      setAiGenerated(true);
    } catch {
      setError("Could not generate draft. Please write your message manually.");
    } finally {
      setDrafting(false);
    }
  }

  async function handleSend() {
    if (!body.trim()) {
      setError("Message body cannot be empty.");
      return;
    }
    setSending(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/employer/me/outreach/send`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          match_id: matchId,
          applicant_id: applicantId,
          job_id: jobId,
          subject,
          body,
          ai_generated: aiGenerated,
        }),
      });
      if (!res.ok) throw new Error("Send failed");
      const data = await res.json().catch(() => ({} as { outreach_id?: string }));
      const outreachId = data.outreach_id ?? null;
      setSentOutreachId(outreachId);
      setSent(true);
      // 10-second undo toast — rollback deletes the outreach record if invoked.
      toast.undo(
        "Marked sent.",
        async () => {
          if (!outreachId) return;
          try {
            await fetch(`${API_URL}/employer/me/outreach/${outreachId}`, {
              method: "DELETE",
              headers: { Authorization: `Bearer ${token}` },
            });
            setSent(false);
            setSentOutreachId(null);
          } catch {
            // Best effort — if the API doesn't support DELETE yet, we simply
            // let the user re-open the modal to correct.
          }
        },
        { duration: 10000 },
      );
    } catch {
      setError("Could not record outreach. Please try again.");
    } finally {
      setSending(false);
    }
  }

  return (
    <motion.div
      className="fixed inset-0 bg-studio-dark-cork/30 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3, ease: easeCohere }}
      onClick={onClose}
    >
      <motion.div
        className="bg-white rounded-lg w-full max-w-lg border border-border-light shadow-xl"
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 12 }}
        transition={{ duration: 0.3, ease: easeCohere }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-hairline">
          <div>
            <h2 className="font-display text-feature text-cohere-ink leading-tight">Reach out to {applicantName}</h2>
            <p className="text-caption text-slate-muted mt-1">Re: {jobTitle}</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-muted hover:text-ink transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {sent ? (
          <div className="p-10 text-center">
            <CheckCircle2 className="w-12 h-12 text-cohere-green mx-auto mb-3" />
            <p className="font-display text-feature text-cohere-ink">Outreach recorded!</p>
            <p className="text-body text-slate mt-1">
              This has been saved to your outreach history.
            </p>
            <button onClick={onClose} className="btn-primary mt-6">
              Done
            </button>
          </div>
        ) : (
          <div className="p-6 space-y-5">
            {/* AI draft button */}
            <button
              onClick={handleDraft}
              disabled={drafting}
              className="inline-flex items-center gap-2 text-caption font-medium text-cohere-blue border border-cohere-blue/20 bg-wash-blue rounded-pill px-4 py-2 hover:bg-cohere-blue/5 transition-colors disabled:opacity-50"
            >
              {drafting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Sparkles className="w-3.5 h-3.5" />
              )}
              {drafting ? "Generating draft…" : "Generate AI draft"}
            </button>

            {/* Subject */}
            <div>
              <label className="block text-micro font-medium tracking-wide text-slate-muted mb-2">Subject</label>
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="e.g. Opportunity: Welder position at Acme Industries"
                className="input-cohere"
              />
            </div>

            {/* Body */}
            <div>
              <label className="block text-micro font-medium tracking-wide text-slate-muted mb-2">Message</label>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={6}
                placeholder="Write your outreach message here, or use the AI draft button above…"
                className="input-cohere resize-none"
              />
            </div>

            {error && <p className="text-body text-error-red">{error}</p>}

            {/* Actions */}
            <div className="flex items-center justify-end gap-4 pt-3 border-t border-hairline">
              <button onClick={onClose} className="btn-secondary">
                Cancel
              </button>
              <button
                onClick={handleSend}
                disabled={sending || !body.trim()}
                className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {sending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                {sending ? "Saving…" : "Mark as sent"}
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}
