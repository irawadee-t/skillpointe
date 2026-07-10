"use client";

import { useState } from "react";
import { Loader2, Check, Mail, MessageSquare, KeyRound, ShieldAlert } from "lucide-react";

import {
  confirmEmailChange, confirmPhoneChange,
  requestEmailChange, requestPhoneChange, startSkilledIdRecovery,
} from "@/lib/api/transactions";
import { PageHeader, MonoLabel } from "@/components/ui";

/**
 * Two-step change flows for email + phone (request → 6-digit code → confirm).
 * SKILLED ID recovery is a single-step submission that opens an admin ticket.
 *
 * All three share the same card language so the settings page reads cleanly.
 */
export function AccountSettingsClient({ token, initialEmail }: { token: string; initialEmail: string }) {
  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Account"
          title="Account settings"
          lead="Change how we reach you, or ask us to restore access to your SKILLED ID."
        />

        <EmailChangeCard token={token} currentEmail={initialEmail} />
        <PhoneChangeCard token={token} />
        <SkilledIdRecoveryCard token={token} />
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
function EmailChangeCard({ token, currentEmail }: { token: string; currentEmail: string }) {
  const [phase, setPhase] = useState<"idle" | "code" | "done">("idle");
  const [newEmail, setNewEmail] = useState("");
  const [masked, setMasked] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function requestCode() {
    setBusy(true); setErr(null);
    try {
      const r = await requestEmailChange(token, newEmail.trim());
      setMasked(r.masked_target ?? newEmail);
      setPhase("code");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not send code.");
    } finally { setBusy(false); }
  }

  async function confirmCode() {
    setBusy(true); setErr(null);
    try {
      await confirmEmailChange(token, code.trim());
      setPhase("done");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Wrong code.");
    } finally { setBusy(false); }
  }

  return (
    <Card icon={Mail} title="Change email">
      <p className="text-body text-slate">Current: <span className="font-medium text-cohere-ink">{currentEmail}</span></p>
      {err && <p className="mt-3 text-caption text-studio-maroon">{err}</p>}

      {phase === "idle" && (
        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="block flex-1">
            <MonoLabel className="mb-1 block">New email</MonoLabel>
            <input type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} className="input-cohere" placeholder="you@newdomain.com" />
          </label>
          <button onClick={requestCode} disabled={busy || !newEmail.trim()} className="btn-primary inline-flex items-center gap-1.5">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Send code
          </button>
        </div>
      )}

      {phase === "code" && (
        <div className="mt-4 rounded-lg border border-cohere-blue/30 bg-wash-blue p-4">
          <p className="text-body text-cohere-ink">
            We sent a 6-digit code to <strong>{masked}</strong>. Enter it below within 20 minutes.
          </p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
            <input
              inputMode="numeric" autoComplete="one-time-code" maxLength={6}
              value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              className="input-cohere flex-1 text-center text-lg tracking-widest"
              placeholder="000000"
            />
            <button onClick={confirmCode} disabled={busy || code.length !== 6} className="btn-primary inline-flex items-center gap-1.5">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Confirm
            </button>
          </div>
          <button onClick={() => { setPhase("idle"); setCode(""); }} className="mt-2 text-caption text-slate hover:text-cohere-ink">
            Use a different email
          </button>
        </div>
      )}

      {phase === "done" && (
        <div className="mt-4 rounded-lg border border-cohere-green/30 bg-wash-green p-4 text-body text-cohere-ink">
          <Check className="mr-1 inline h-4 w-4 text-cohere-green" /> Email updated. Sign in with your new address next time.
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
function PhoneChangeCard({ token }: { token: string }) {
  const [phase, setPhase] = useState<"idle" | "code" | "done">("idle");
  const [newPhone, setNewPhone] = useState("");
  const [masked, setMasked] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function requestCode() {
    setBusy(true); setErr(null);
    try {
      const r = await requestPhoneChange(token, newPhone.trim());
      setMasked(r.masked_target ?? newPhone);
      setPhase("code");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not send code.");
    } finally { setBusy(false); }
  }

  async function confirmCode() {
    setBusy(true); setErr(null);
    try {
      await confirmPhoneChange(token, code.trim());
      setPhase("done");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Wrong code.");
    } finally { setBusy(false); }
  }

  return (
    <Card icon={MessageSquare} title="Change phone">
      <p className="text-body text-slate">We text this number when a match comes up or an employer sends an interview time.</p>
      {err && <p className="mt-3 text-caption text-studio-maroon">{err}</p>}

      {phase === "idle" && (
        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="block flex-1">
            <MonoLabel className="mb-1 block">New phone</MonoLabel>
            <input inputMode="tel" value={newPhone} onChange={(e) => setNewPhone(e.target.value)} className="input-cohere" placeholder="(770) 555-1234" />
          </label>
          <button onClick={requestCode} disabled={busy || newPhone.length < 7} className="btn-primary inline-flex items-center gap-1.5">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Send code
          </button>
        </div>
      )}

      {phase === "code" && (
        <div className="mt-4 rounded-lg border border-cohere-blue/30 bg-wash-blue p-4">
          <p className="text-body text-cohere-ink">
            We texted a 6-digit code to <strong>{masked}</strong>. Enter it below within 20 minutes.
          </p>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
            <input
              inputMode="numeric" autoComplete="one-time-code" maxLength={6}
              value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              className="input-cohere flex-1 text-center text-lg tracking-widest"
              placeholder="000000"
            />
            <button onClick={confirmCode} disabled={busy || code.length !== 6} className="btn-primary inline-flex items-center gap-1.5">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Confirm
            </button>
          </div>
          <button onClick={() => { setPhase("idle"); setCode(""); }} className="mt-2 text-caption text-slate hover:text-cohere-ink">
            Use a different number
          </button>
        </div>
      )}

      {phase === "done" && (
        <div className="mt-4 rounded-lg border border-cohere-green/30 bg-wash-green p-4 text-body text-cohere-ink">
          <Check className="mr-1 inline h-4 w-4 text-cohere-green" /> Phone updated.
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
function SkilledIdRecoveryCard({ token }: { token: string }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (reason.trim().length < 10) { setErr("Please give us a bit of detail (10+ characters)."); return; }
    setBusy(true); setErr(null);
    try {
      await startSkilledIdRecovery(token, reason.trim());
      setDone(true);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not open ticket.");
    } finally { setBusy(false); }
  }

  return (
    <Card icon={KeyRound} title="SKILLED ID recovery" tone="coral">
      <p className="text-body text-slate">
        If you can't get into your SKILLED ID or your credentials, tell us what happened. A SKILLED Nation admin reads every ticket and gets back within one business day.
      </p>
      {err && <p className="mt-3 text-caption text-studio-maroon">{err}</p>}

      {done ? (
        <div className="mt-4 rounded-lg border border-cohere-green/30 bg-wash-green p-4 text-body text-cohere-ink">
          <Check className="mr-1 inline h-4 w-4 text-cohere-green" />
          Ticket opened. An admin will reach out at the email + phone we have on file. Usual response: within 1 business day.
        </div>
      ) : (
        <>
          <textarea
            value={reason} onChange={(e) => setReason(e.target.value)}
            rows={4}
            placeholder="What happened, when, and how we can reach you. Include any employer or training-partner references we can use to verify you."
            className="input-cohere mt-4 resize-y"
            maxLength={2000}
          />
          <div className="mt-3 flex items-center justify-between">
            <span className="inline-flex items-center gap-1 text-caption text-slate-muted"><ShieldAlert className="h-3.5 w-3.5" /> Verified via admin — for your safety, not self-serve.</span>
            <button onClick={submit} disabled={busy || reason.trim().length < 10} className="btn-primary inline-flex items-center gap-1.5">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
              Open recovery ticket
            </button>
          </div>
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
function Card({
  icon: Icon, title, children, tone = "neutral",
}: {
  icon: typeof Mail; title: string; children: React.ReactNode;
  tone?: "neutral" | "coral";
}) {
  const border = tone === "coral" ? "border-studio-maroon/30 bg-studio-maroon/[0.03]" : "border-hairline bg-white";
  const iconTone = tone === "coral" ? "text-studio-maroon" : "text-cohere-green";
  return (
    <section className={`rounded-xl border ${border} p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]`}>
      <div className="flex items-center gap-2">
        <Icon className={`h-5 w-5 ${iconTone}`} strokeWidth={1.75} />
        <h2 className="font-display text-feature text-cohere-ink">{title}</h2>
      </div>
      <div className="mt-2">{children}</div>
    </section>
  );
}
