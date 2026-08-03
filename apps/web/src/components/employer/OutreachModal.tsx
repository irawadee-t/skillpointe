"use client";

/**
 * OutreachModal — employer reach-out dialog for a matched candidate.
 *
 * SKILLED does NOT send this message. The flow is explicitly assisted:
 *  1. Draft (AI or manual)
 *  2. Copy the message, or open it in your own email app (mailto)
 *  3. "Log this outreach" — records in employer_outreach that YOU sent it
 *     (enabled only after copy/open, so the analytics stay truthful:
 *     logged = the employer confirmed they sent it themselves).
 */
import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { X, Sparkles, Loader2, CheckCircle2, Copy, Check, ExternalLink, ClipboardCheck } from "lucide-react";
import { easeCohere } from "@/lib/motion";
import { useToast } from "@/components/ui";
import { API_BASE } from "@/lib/api/client";

interface OutreachModalProps {
  matchId: string;
  applicantId: string;
  jobId: string;
  applicantName: string;
  jobTitle: string;
  token: string;
  onClose: () => void;
}

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
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  // The employer must take the message somewhere (clipboard or their email
  // app) before they can log it as sent — keeps outreach analytics honest.
  const [exported, setExported] = useState(false);
  const [copied, setCopied] = useState(false);

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  // Close, but guard an in-progress draft: if the body has content and we
  // haven't already recorded the outreach, ask before discarding.
  function requestClose() {
    if (!sent && body.trim().length > 0) {
      setConfirmDiscard(true);
      return;
    }
    onClose();
  }

  // Capture prior focus on mount, move focus into the dialog, restore on unmount.
  useEffect(() => {
    previouslyFocusedRef.current = (document.activeElement as HTMLElement) ?? null;
    const t = setTimeout(() => dialogRef.current?.focus(), 10);
    return () => {
      clearTimeout(t);
      previouslyFocusedRef.current?.focus?.();
    };
  }, []);

  // Escape-to-close (routed through the discard guard) + Tab focus trap.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        if (confirmDiscard) { setConfirmDiscard(false); return; }
        requestClose();
        return;
      }
      if (e.key !== "Tab") return;
      const root = dialogRef.current;
      if (!root) return;
      const focusables = root.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey && (active === first || active === root)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmDiscard, sent, body]);

  async function handleDraft() {
    setDrafting(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/employer/me/outreach/draft`, {
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

  async function handleCopy() {
    const text = subject.trim() ? `Subject: ${subject.trim()}\n\n${body}` : body;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setExported(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Could not copy. Select the text and copy it manually.");
    }
  }

  function handleMailto() {
    const url = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    window.open(url, "_blank");
    setExported(true);
  }

  async function handleSend() {
    if (!body.trim()) {
      setError("Message body cannot be empty.");
      return;
    }
    setSending(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/employer/me/outreach/send`, {
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
        "Outreach logged.",
        async () => {
          if (!outreachId) return;
          try {
            await fetch(`${API_BASE}/employer/me/outreach/${outreachId}`, {
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
      onClick={requestClose}
    >
      <motion.div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Reach out to ${applicantName}`}
        tabIndex={-1}
        className="relative bg-white rounded-lg w-full max-w-lg border border-border-light shadow-xl focus:outline-none"
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 12 }}
        transition={{ duration: 0.3, ease: easeCohere }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-hairline">
          <div>
            <h2 className="text-[1.0625rem] font-medium text-cohere-ink leading-tight">Reach out to {applicantName}</h2>
            <p className="text-caption text-slate-muted mt-1">Re: {jobTitle}</p>
          </div>
          <button
            onClick={requestClose}
            aria-label="Close dialog"
            className="text-slate-muted hover:text-ink transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Confirm-before-discard — shown when closing with an unsaved draft. */}
        {confirmDiscard && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-white/95 p-6 backdrop-blur-sm">
            <div className="max-w-sm text-center">
              <p className="text-[1.0625rem] font-medium text-cohere-ink">Discard this draft?</p>
              <p className="text-body text-slate mt-1">
                Your unsent message will be lost.
              </p>
              <div className="mt-5 flex items-center justify-center gap-3">
                <button
                  onClick={() => setConfirmDiscard(false)}
                  className="btn-secondary"
                >
                  Keep editing
                </button>
                <button
                  onClick={onClose}
                  className="rounded-pill bg-error-red px-4 py-2 text-caption font-medium text-white hover:opacity-90"
                >
                  Discard
                </button>
              </div>
            </div>
          </div>
        )}

        {sent ? (
          <div className="p-10 text-center">
            <CheckCircle2 className="w-12 h-12 text-cohere-green mx-auto mb-3" />
            <p className="text-[1.0625rem] font-medium text-cohere-ink">Outreach logged</p>
            <p className="text-body text-slate mt-1">
              Saved to your outreach history as sent by you. SKILLED did not send the message.
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
              className="inline-flex items-center gap-2 text-caption font-medium text-cohere-blue border border-cohere-blue/40 bg-white rounded-pill px-4 py-2 hover:border-cohere-blue transition-colors disabled:opacity-50"
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

            {/* Assisted send — SKILLED never sends this message itself. */}
            <div className="rounded-md border border-hairline bg-stone/30 p-3">
              <p className="text-caption text-slate">
                SKILLED doesn&apos;t send this message for you. Copy it or open it in
                your email app, send it yourself, then log the outreach here.
              </p>
              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                <button
                  onClick={handleCopy}
                  disabled={!body.trim()}
                  className="btn-pill-outline text-micro disabled:opacity-50"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-cohere-green" /> : <Copy className="w-3.5 h-3.5" />}
                  {copied ? "Copied" : "Copy message"}
                </button>
                <button
                  onClick={handleMailto}
                  disabled={!body.trim()}
                  className="btn-pill-outline text-micro disabled:opacity-50"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Open in your email app
                </button>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-4 pt-3 border-t border-hairline">
              <button onClick={requestClose} className="btn-secondary">
                Cancel
              </button>
              <div className="flex flex-col items-end">
                <button
                  onClick={handleSend}
                  disabled={sending || !body.trim() || !exported}
                  className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {sending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <ClipboardCheck className="w-4 h-4" />
                  )}
                  {sending ? "Saving…" : "Log this outreach"}
                </button>
                {!exported && body.trim() && (
                  <span className="mt-1 text-micro text-slate-muted">
                    Copy or open the message first
                  </span>
                )}
              </div>
            </div>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}
