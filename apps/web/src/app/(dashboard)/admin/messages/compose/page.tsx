/**
 * Admin — Compose Platform Message (stub)
 *
 * Minimal compose form so "Send message" from the applicants directory has
 * a real destination instead of a mailto: link. The DM compose endpoint
 * isn't wired yet (see task #145); the submit fails gracefully with a toast.
 */
"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { MessageSquare, Loader2, User } from "lucide-react";

import { PageHeader, Breadcrumb, useToast } from "@/components/ui";

function ComposeInner() {
  const searchParams = useSearchParams();
  const applicantId = searchParams.get("applicant_id") ?? "";
  const employerId = searchParams.get("employer_id") ?? "";
  const recipientId = applicantId || employerId;
  const recipientType = applicantId ? "applicant" : employerId ? "employer" : "";

  const [body, setBody] = useState("");
  const [alsoEmail, setAlsoEmail] = useState(true);
  const [sending, setSending] = useState(false);
  const toast = useToast();

  // Recipient details are passed by query string only for this stub. A future
  // pass will hydrate the chip from the API once the DM endpoint exists.
  const [recipientLabel, setRecipientLabel] = useState<string>("");

  useEffect(() => {
    if (!recipientId) return;
    // Placeholder label; real fetch lands with task #145.
    setRecipientLabel(`${recipientType} ${recipientId.slice(0, 8)}…`);
  }, [recipientId, recipientType]);

  async function onSend(e: React.FormEvent) {
    e.preventDefault();
    if (!recipientId || !body.trim() || sending) return;
    setSending(true);
    try {
      const res = await fetch("/api/admin/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipient_id: recipientId,
          recipient_type: recipientType,
          body: body.trim(),
          notify_by_email: alsoEmail,
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      toast.success("Message sent.");
      setBody("");
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("[admin/messages/compose] send failed", err);
      toast.info("Coming soon (task #145) — platform messaging isn't wired up yet.");
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb
          items={[
            { label: "Admin", href: "/admin" },
            { label: "Applicants", href: "/admin/applicants" },
            { label: "Compose" },
          ]}
        />
        <PageHeader
          eyebrow="Messaging"
          title="Compose platform message"
          lead="Send a message that reaches the recipient in-app, with an optional email notification."
          actions={
            <Link href="/admin/applicants" className="btn-secondary">
              ← Back
            </Link>
          }
        />

        <form onSubmit={onSend} className="rounded-md border border-border-light bg-white p-5 space-y-4">
          <div>
            <label className="mono-label mb-1.5 block">Recipient</label>
            <div className="inline-flex items-center gap-2 rounded-full border border-hairline bg-stone px-3 py-1.5 text-caption text-cohere-ink">
              <User className="h-3.5 w-3.5 text-slate-muted" />
              {recipientLabel || "No recipient — open this page from an applicant row."}
            </div>
          </div>

          <div>
            <label className="mono-label mb-1.5 block" htmlFor="msg-body">
              Message
            </label>
            <textarea
              id="msg-body"
              className="input-cohere min-h-[160px]"
              placeholder="Write your message…"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              required
            />
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-caption text-slate">
            <input
              type="checkbox"
              checked={alsoEmail}
              onChange={(e) => setAlsoEmail(e.target.checked)}
              className="h-4 w-4 accent-cohere-green"
            />
            Also notify by email
          </label>

          <div className="flex items-center gap-3 border-t border-hairline pt-4">
            <button
              type="submit"
              disabled={sending || !recipientId || !body.trim()}
              className="btn-primary"
            >
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageSquare className="h-4 w-4" />}
              Send platform message
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}

export default function ComposeMessagePage() {
  return (
    <Suspense
      fallback={
        <main className="py-8">
          <div className="page-shell text-caption text-slate">Loading…</div>
        </main>
      }
    >
      <ComposeInner />
    </Suspense>
  );
}
