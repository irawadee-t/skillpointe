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
import { X, Sparkles, Loader2, Send, CheckCircle2 } from "lucide-react";

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
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [aiGenerated, setAiGenerated] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
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
      setSent(true);
    } catch {
      setError("Could not record outreach. Please try again.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl w-full max-w-lg border border-zinc-200">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-zinc-200">
          <div>
            <h2 className="font-semibold text-zinc-900">Reach out to {applicantName}</h2>
            <p className="text-xs text-zinc-400 mt-0.5">Re: {jobTitle}</p>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-600 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {sent ? (
          <div className="p-8 text-center">
            <CheckCircle2 className="w-12 h-12 text-emerald-600 mx-auto mb-3" />
            <p className="font-medium text-zinc-900">Outreach recorded!</p>
            <p className="text-sm text-zinc-500 mt-1">
              This has been saved to your outreach history.
            </p>
            <button
              onClick={onClose}
              className="mt-5 px-5 py-2 bg-zinc-900 text-white text-sm font-medium rounded-full hover:bg-zinc-700 transition-colors"
            >
              Done
            </button>
          </div>
        ) : (
          <div className="p-5 space-y-4">
            {/* AI draft button */}
            <button
              onClick={handleDraft}
              disabled={drafting}
              className="inline-flex items-center gap-2 text-sm font-medium text-spf-navy border border-spf-navy/20 rounded-full px-3 py-1.5 hover:bg-spf-navy/10 transition-colors"
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
              <label className="block text-xs text-zinc-400 mb-1">Subject</label>
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="e.g. Opportunity: Welder position at Acme Industries"
                className="w-full border border-zinc-200 rounded-lg px-3 py-2 text-sm bg-white text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-spf-navy/20 focus:border-spf-navy"
              />
            </div>

            {/* Body */}
            <div>
              <label className="block text-xs text-zinc-400 mb-1">Message</label>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={6}
                placeholder="Write your outreach message here, or use the AI draft button above…"
                className="w-full border border-zinc-200 rounded-lg px-3 py-2 text-sm bg-white text-zinc-900 placeholder:text-zinc-400 resize-none focus:outline-none focus:ring-1 focus:ring-spf-navy/20 focus:border-spf-navy"
              />
            </div>

            {error && <p className="text-sm text-rose-600">{error}</p>}

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 pt-2 border-t border-zinc-200">
              <button
                onClick={onClose}
                className="text-sm text-zinc-400 hover:text-zinc-600 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSend}
                disabled={sending || !body.trim()}
                className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white text-sm font-medium rounded-full hover:bg-zinc-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
      </div>
    </div>
  );
}
