"use client";

import { useEffect, useState } from "react";
import {
  Loader2, Check, Mail, MessageSquare, KeyRound, ShieldAlert, Download,
  CalendarDays, Unplug,
} from "lucide-react";

import { API_BASE } from "@/lib/api/client";

import {
  CalendarConnection, CalendarProviders,
  confirmEmailChange, confirmPhoneChange, connectDemoCalendar,
  disconnectCalendarConnection, getCalendarConnections, getCalendarProviders,
  requestEmailChange, requestPhoneChange, startCalendarConnect,
  startSkilledIdRecovery,
} from "@/lib/api/transactions";
import { CalendarSubscribeCard } from "@/components/interviews/CalendarSubscribeCard";
import { PageHeader, MonoLabel } from "@/components/ui";

/**
 * Two-step change flows for email + phone (request → 6-digit code → confirm).
 * Account recovery is a single-step submission that opens an admin ticket.
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
          lead="Change how we reach you, or ask us to restore access to your account."
        />

        <EmailChangeCard token={token} currentEmail={initialEmail} />
        <PhoneChangeCard token={token} />
        <CalendarCard token={token} />
        <AccountRecoveryCard token={token} />
        <DownloadDataCard token={token} />
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
const PROVIDER_LABELS: Record<CalendarConnection["provider"], string> = {
  google: "Google Calendar",
  microsoft: "Outlook",
  demo: "Demo calendar",
};

function CalendarCard({ token }: { token: string }) {
  const [connections, setConnections] = useState<CalendarConnection[] | null>(null);
  const [providers, setProviders] = useState<CalendarProviders | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // provider being connected / id being removed
  const [flash, setFlash] = useState<"connected" | "error" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    // OAuth callback lands on /account/settings?calendar=connected#calendar.
    // Read the flag once, then clean the URL so refreshes don't re-announce.
    const params = new URLSearchParams(window.location.search);
    const status = params.get("calendar");
    if (status === "connected" || status === "error") {
      setFlash(status);
      params.delete("calendar");
      const rest = params.toString();
      window.history.replaceState(
        null, "",
        window.location.pathname + (rest ? `?${rest}` : "") + window.location.hash,
      );
    }
  }, []);

  useEffect(() => {
    let alive = true;
    Promise.all([
      getCalendarConnections(token).catch(() => [] as CalendarConnection[]),
      getCalendarProviders(token).catch(() => null),
    ]).then(([conns, provs]) => {
      if (!alive) return;
      setConnections(conns);
      setProviders(provs);
    });
    return () => { alive = false; };
  }, [token]);

  async function connect(provider: "google" | "microsoft") {
    setBusy(provider); setErr(null);
    try {
      const { authorize_url } = await startCalendarConnect(token, provider);
      window.location.assign(authorize_url);
      // Navigation takes over; no need to reset `busy`.
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not start the connection.");
      setBusy(null);
    }
  }

  async function connectDemo() {
    setBusy("demo"); setErr(null);
    try {
      const conn = await connectDemoCalendar(token);
      setConnections((prev) => {
        const rest = (prev ?? []).filter((c) => c.id !== conn.id);
        return [...rest, conn];
      });
      setFlash("connected");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not connect the demo calendar.");
    } finally {
      setBusy(null);
    }
  }

  async function disconnect(id: string) {
    setBusy(id); setErr(null);
    try {
      await disconnectCalendarConnection(token, id);
      setConnections((prev) => (prev ?? []).filter((c) => c.id !== id));
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not disconnect.");
    } finally {
      setBusy(null);
    }
  }

  const anyProvider =
    providers?.google_configured || providers?.outlook_configured || providers?.demo_available;

  return (
    <div id="calendar" className="scroll-mt-6 space-y-4">
      <Card icon={CalendarDays} title="Calendar">
        <p className="text-body text-slate">
          Connect your calendar to see your busy times behind the interview time
          grid. We read free/busy only — never event titles, guests, or details.
        </p>

        {flash === "connected" && (
          <div className="mt-3 rounded-lg border border-cohere-green/30 bg-wash-green p-3 text-body text-cohere-ink">
            <Check className="mr-1 inline h-4 w-4 text-cohere-green" /> Calendar connected. Your
            busy times now show on the interview grid.
          </div>
        )}
        {flash === "error" && (
          <div className="mt-3 rounded-lg border border-hairline bg-white p-3 text-body text-cohere-ink">
            The connection didn&rsquo;t finish. Nothing was saved. Try again below.
          </div>
        )}
        {err && <p className="mt-3 text-caption text-studio-maroon" role="alert">{err}</p>}

        {connections === null ? (
          <p className="mt-4 inline-flex items-center gap-2 text-caption text-slate">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading your connections…
          </p>
        ) : connections.length > 0 ? (
          <ul className="mt-4 divide-y divide-hairline rounded-[10px] border border-hairline bg-white">
            {connections.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-body font-medium text-cohere-ink">
                    {PROVIDER_LABELS[c.provider] ?? c.provider}
                    {c.provider === "demo" && (
                      <span className="ml-2 rounded-full border border-hairline bg-white px-2 py-0.5 text-[11px] font-medium text-slate">
                        Demo
                      </span>
                    )}
                  </p>
                  <p className="truncate text-caption text-slate-muted">
                    {c.account_email || "Connected account"} · since{" "}
                    {new Date(c.connected_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => disconnect(c.id)}
                  disabled={busy === c.id}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-hairline bg-white px-3 py-1.5 text-caption font-medium text-cohere-ink transition-colors duration-200 hover:border-cohere-ink"
                >
                  {busy === c.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Unplug className="h-3.5 w-3.5" />}
                  Disconnect
                </button>
              </li>
            ))}
          </ul>
        ) : anyProvider ? (
          <p className="mt-4 text-caption text-slate-muted">
            No calendar connected yet.
          </p>
        ) : (
          <p className="mt-4 text-caption text-slate-muted">
            Calendar connections aren&rsquo;t configured on this deployment yet. You can still
            subscribe to your interviews below.
          </p>
        )}

        {(providers?.google_configured || providers?.outlook_configured || providers?.demo_available) && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {providers?.google_configured && (
              <button
                type="button"
                onClick={() => connect("google")}
                disabled={busy === "google"}
                className="btn-secondary inline-flex items-center gap-1.5"
              >
                {busy === "google" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Connect Google Calendar
              </button>
            )}
            {providers?.outlook_configured && (
              <button
                type="button"
                onClick={() => connect("microsoft")}
                disabled={busy === "microsoft"}
                className="btn-secondary inline-flex items-center gap-1.5"
              >
                {busy === "microsoft" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Connect Outlook
              </button>
            )}
            {providers?.demo_available && !connections?.some((c) => c.provider === "demo") && (
              <button
                type="button"
                onClick={connectDemo}
                disabled={busy === "demo"}
                className="btn-secondary inline-flex items-center gap-1.5"
              >
                {busy === "demo" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Connect demo calendar
              </button>
            )}
          </div>
        )}
        {providers?.demo_available && (
          <p className="mt-2 text-micro text-slate-muted">
            The demo calendar is a local development fixture with made-up busy times. It never
            appears in production.
          </p>
        )}
      </Card>

      {/* The other half of calendar life: your interviews OUT to your calendar
          app via the personal ICS subscription feed. */}
      <CalendarSubscribeCard token={token} />
    </div>
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
function AccountRecoveryCard({ token }: { token: string }) {
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
    <Card icon={KeyRound} title="Account recovery" tone="coral">
      <p className="text-body text-slate">
        If you can't get into your account or your credentials, tell us what happened. A SKILLED Nation admin reads every ticket and gets back within one business day.
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
            <span className="inline-flex items-center gap-1 text-caption text-slate-muted"><ShieldAlert className="h-3.5 w-3.5" /> Verified via admin, for your safety, not self-serve.</span>
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
function DownloadDataCard({ token }: { token: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${API_BASE}/me/account/export`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) throw new Error(String(r.status));
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `skilled-nation-data-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      setError("Couldn't prepare your export. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card icon={Download} title="Download your data">
      <p className="text-body text-slate">
        Get a complete copy of the data we hold about you (profile, credentials,
        matches, applications, and messages) as a JSON file.
      </p>
      <button onClick={download} disabled={busy} className="btn-secondary mt-4 inline-flex items-center gap-2">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
        Download my data
      </button>
      {error && <p className="mt-2 text-caption text-error-red">{error}</p>}
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
        <h2 className="text-[1.0625rem] font-medium text-cohere-ink">{title}</h2>
      </div>
      <div className="mt-2">{children}</div>
    </section>
  );
}
