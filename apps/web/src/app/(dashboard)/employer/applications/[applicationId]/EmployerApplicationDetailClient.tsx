"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft, Calendar, Check, Loader2, Plus, ShieldAlert, Trash2, X, Send, Video, MapPin,
} from "lucide-react";

import {
  Application, InterviewSlot,
  getEmployerApplication, patchEmployerApplication, proposeInterviewSlots,
} from "@/lib/api/transactions";
import { PageHeader, MonoLabel, CopyableText, Breadcrumb } from "@/components/ui";

/**
 * Employer's application detail — snapshot review, status transitions,
 * and Calendly-style interview proposal (3–5 time slots).
 */
export function EmployerApplicationDetailClient({ token, applicationId }: { token: string; applicationId: string }) {
  const [app, setApp] = useState<Application | null>(null);
  const [slots, setSlots] = useState<InterviewSlot[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [proposing, setProposing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    try {
      const a = await getEmployerApplication(token, applicationId);
      setApp(a);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not load");
    }
  }
  useEffect(() => { load(); }, [token, applicationId]);

  function knockoutPrompt(): string | null {
    if (!app) return null;
    const failed = app.screening_answers.filter((a) => a.knockout_pass === false);
    if (failed.length === 0) return null;
    const which = failed.map((a) => `"${a.prompt}"`).join(", ");
    return `This candidate flagged ${which} screening question — continue anyway?`;
  }

  async function setStatus(status: string, note?: string) {
    // Guard destructive-forward actions if knockout screening flagged.
    if (["shortlisted", "hired"].includes(status)) {
      const prompt = knockoutPrompt();
      if (prompt && !confirm(prompt)) return;
    }
    setBusy(status);
    try {
      const next = await patchEmployerApplication(token, applicationId, { status, decision_note: note });
      setApp(next);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not update");
    } finally { setBusy(null); }
  }

  function startProposing() {
    const prompt = knockoutPrompt();
    if (prompt && !confirm(prompt)) return;
    setProposing((v) => !v);
  }

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[
          { label: "Applications", href: "/employer/applications" },
          { label: app?.applicant_name ?? "Applicant" },
        ]} />

        {err && <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4">{err}</div>}
        {app === null && !err && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}

        {app && (
          <>
            <PageHeader
              eyebrow={`${app.applicant_name} — applied ${new Date(app.submitted_at).toLocaleDateString()}`}
              title={app.job_title}
              lead={app.knockout_failed
                ? "One of this applicant's screening answers didn't match a hard requirement — worth a careful read."
                : "Read the snapshot, then move them forward or propose interview times."}
              actions={<StatusPill status={app.status} />}
            />

            {app.knockout_failed && (
              <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4 text-body text-cohere-ink">
                <ShieldAlert className="mr-1 inline h-4 w-4 text-studio-maroon" />
                Screening flag — see the applicant's answers below.
              </div>
            )}

            {/* Action toolbar */}
            <div className="flex flex-wrap gap-2">
              {app.status !== "shortlisted" && !["hired","rejected","withdrawn"].includes(app.status) && (
                <button onClick={() => setStatus("shortlisted")} disabled={busy === "shortlisted"} className="btn-pill-outline inline-flex items-center gap-1.5">
                  {busy === "shortlisted" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                  Shortlist
                </button>
              )}
              {!["hired","rejected","withdrawn"].includes(app.status) && (
                <button onClick={startProposing} className="btn-primary inline-flex items-center gap-1.5">
                  <Calendar className="h-4 w-4" /> Propose interview times
                </button>
              )}
              {app.status !== "hired" && !["rejected","withdrawn"].includes(app.status) && (
                <button onClick={() => setStatus("hired")} disabled={busy === "hired"} className="btn-primary-green inline-flex items-center gap-1.5">
                  {busy === "hired" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                  Mark hired
                </button>
              )}
              {!["hired","rejected","withdrawn"].includes(app.status) && (
                <button onClick={() => setStatus("rejected", "Not a match for this role right now.")} disabled={busy === "rejected"} className="btn-pill-outline inline-flex items-center gap-1.5 border-studio-maroon text-studio-maroon">
                  {busy === "rejected" ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
                  Reject
                </button>
              )}
            </div>

            {proposing && (
              <ProposeInterviewPanel
                token={token}
                applicationId={applicationId}
                onDone={() => { setProposing(false); load(); }}
              />
            )}

            {/* Applicant snapshot */}
            <ApplicantSnapshot app={app} />
          </>
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------

function ApplicantSnapshot({ app }: { app: Application }) {
  const snap = app.resume_snapshot as Record<string, unknown>;
  const skills = (snap.skills as string[] | undefined) ?? [];
  const certs = (snap.certifications as string[] | undefined) ?? [];
  return (
    <section className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
      <h2 className="font-display text-feature text-cohere-ink">Applicant snapshot</h2>
      <p className="mt-1 text-caption text-slate">Captured when they applied. Any profile changes since then aren't shown here.</p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Name"     value={`${snap.first_name || ""} ${snap.last_name || ""}`.trim()} />
        <Field label="Location" value={[snap.city, snap.state].filter(Boolean).join(", ")} />
        <FieldCopy label="Phone" value={snap.phone as string | undefined} />
        <FieldCopy label="Email" value={snap.email as string | undefined} />
        <Field label="Trade / program" value={snap.program_name_raw as string | undefined} />
        <Field label="Years experience" value={snap.years_experience ? String(snap.years_experience) : undefined} />
      </div>

      {typeof snap.career_goals_raw === "string" && snap.career_goals_raw && (
        <div className="mt-4">
          <MonoLabel className="mb-1 block">Career goals</MonoLabel>
          <p className="whitespace-pre-line text-body text-cohere-ink">{snap.career_goals_raw}</p>
        </div>
      )}

      {typeof snap.experience_raw === "string" && snap.experience_raw && (
        <div className="mt-4">
          <MonoLabel className="mb-1 block">Experience</MonoLabel>
          <p className="whitespace-pre-line text-body text-cohere-ink">{String(snap.experience_raw)}</p>
        </div>
      )}

      {(certs.length > 0 || skills.length > 0) && (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {certs.length > 0 && (
            <div>
              <MonoLabel className="mb-1.5 block">Credentials</MonoLabel>
              <div className="flex flex-wrap gap-1.5">
                {certs.map((c) => <span key={c} className="rounded-full border border-cohere-green/30 bg-wash-green px-2.5 py-0.5 text-micro text-cohere-ink">{c}</span>)}
              </div>
            </div>
          )}
          {skills.length > 0 && (
            <div>
              <MonoLabel className="mb-1.5 block">Skills</MonoLabel>
              <div className="flex flex-wrap gap-1.5">
                {skills.map((s) => <span key={s} className="rounded-full border border-hairline bg-stone/40 px-2.5 py-0.5 text-micro text-slate">{s}</span>)}
              </div>
            </div>
          )}
        </div>
      )}

      {app.cover_note && (
        <div className="mt-4">
          <MonoLabel className="mb-1 block">Note to you</MonoLabel>
          <p className="whitespace-pre-line text-body text-cohere-ink">{app.cover_note}</p>
        </div>
      )}

      {app.screening_answers.length > 0 && (
        <div className="mt-5 border-t border-hairline pt-4">
          <MonoLabel className="mb-2 block">Screening</MonoLabel>
          <ul className="space-y-2">
            {app.screening_answers.map((a, i) => (
              <li key={i} className={`rounded-md border p-3 text-body ${a.knockout_pass ? "border-hairline bg-stone/30" : "border-studio-maroon/30 bg-studio-maroon/[0.06]"}`}>
                <p className="text-caption font-medium text-cohere-ink">{a.prompt}</p>
                <p className="mt-0.5 text-caption text-slate">
                  Answer: {a.answer}
                  {!a.knockout_pass && <span className="ml-2 text-studio-maroon">(flag)</span>}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function Field({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div>
      <MonoLabel className="mb-0.5 block">{label}</MonoLabel>
      <p className="text-body text-cohere-ink">{value}</p>
    </div>
  );
}

function FieldCopy({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div>
      <MonoLabel className="mb-0.5 block">{label}</MonoLabel>
      <CopyableText value={value} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Interview proposal panel — pick 3–5 date+time windows
// ---------------------------------------------------------------------------

interface DraftSlot {
  date: string;      // "YYYY-MM-DD"
  start: string;     // "HH:MM"
  duration: number;  // minutes
}

function ProposeInterviewPanel({
  token, applicationId, onDone,
}: { token: string; applicationId: string; onDone: () => void }) {
  const [draft, setDraft] = useState<DraftSlot[]>(defaultSlots());
  const [location, setLocation] = useState("");
  const [meetingUrl, setMeetingUrl] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function update(i: number, patch: Partial<DraftSlot>) {
    setDraft((prev) => prev.map((d, ix) => ix === i ? { ...d, ...patch } : d));
  }
  function remove(i: number) {
    setDraft((prev) => prev.filter((_, ix) => ix !== i));
  }
  function add() {
    if (draft.length >= 5) return;
    setDraft((prev) => [...prev, defaultSlots()[0]]);
  }

  async function submit() {
    setBusy(true); setErr(null);
    try {
      const slots = draft
        .filter((d) => d.date && d.start && d.duration > 0)
        .map((d) => {
          const start = new Date(`${d.date}T${d.start}:00`);
          const end = new Date(start.getTime() + d.duration * 60_000);
          return {
            start_at: start.toISOString(),
            end_at: end.toISOString(),
            location: location.trim() || undefined,
            meeting_url: meetingUrl.trim() || undefined,
            notes: notes.trim() || undefined,
          };
        });
      if (slots.length < 1) { setErr("Add at least one time."); setBusy(false); return; }
      await proposeInterviewSlots(token, applicationId, slots);
      onDone();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not propose");
    } finally { setBusy(false); }
  }

  return (
    <section className="rounded-xl border border-cohere-blue/30 bg-wash-blue p-5">
      <div className="flex items-center gap-2">
        <Calendar className="h-5 w-5 text-cohere-blue" strokeWidth={1.75} />
        <h2 className="font-display text-feature text-cohere-ink">Propose interview times</h2>
      </div>
      <p className="mt-1 text-body text-slate">Offer up to five windows. The applicant picks one; both sides see the confirmed time.</p>

      {err && <p className="mt-3 text-caption text-studio-maroon">{err}</p>}

      <div className="mt-4 space-y-2">
        {draft.map((d, i) => (
          <div key={i} className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_120px_auto] sm:items-center">
            <input type="date" value={d.date} onChange={(e) => update(i, { date: e.target.value })} className="input-cohere text-caption" />
            <input type="time" value={d.start} onChange={(e) => update(i, { start: e.target.value })} className="input-cohere text-caption" />
            <select value={d.duration} onChange={(e) => update(i, { duration: Number(e.target.value) })} className="input-cohere text-caption">
              <option value={15}>15 min</option>
              <option value={30}>30 min</option>
              <option value={45}>45 min</option>
              <option value={60}>1 hour</option>
              <option value={90}>90 min</option>
            </select>
            <button onClick={() => remove(i)} aria-label="Remove" className="rounded-md border border-hairline bg-white p-2 text-slate-muted hover:border-studio-maroon hover:text-studio-maroon">
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>

      {draft.length < 5 && (
        <button onClick={add} className="mt-2 inline-flex items-center gap-1.5 text-caption text-cohere-blue">
          <Plus className="h-3.5 w-3.5" /> Add another time
        </button>
      )}

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <Field2 label="Location (optional)"><input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Southwire — Carrollton, GA" className="input-cohere text-caption" /></Field2>
        <Field2 label="Meeting URL (optional)"><input value={meetingUrl} onChange={(e) => setMeetingUrl(e.target.value)} placeholder="https://" className="input-cohere text-caption" /></Field2>
      </div>
      <div className="mt-3">
        <Field2 label="Note (optional)">
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="What to prepare, who they'll meet, etc." className="input-cohere text-caption resize-y" />
        </Field2>
      </div>

      <div className="mt-4 flex items-center justify-end">
        <button onClick={submit} disabled={busy} className="btn-primary inline-flex items-center gap-1.5">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          Send {draft.length} time{draft.length === 1 ? "" : "s"} to applicant
        </button>
      </div>
    </section>
  );
}

function Field2({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <MonoLabel className="mb-1 block">{label}</MonoLabel>
      {children}
    </label>
  );
}

function defaultSlots(): DraftSlot[] {
  const t = new Date();
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const tmr = new Date(t); tmr.setDate(t.getDate() + 1);
  const day2 = new Date(t); day2.setDate(t.getDate() + 2);
  return [
    { date: iso(tmr),  start: "10:00", duration: 30 },
    { date: iso(tmr),  start: "14:00", duration: 30 },
    { date: iso(day2), start: "10:00", duration: 30 },
    { date: iso(day2), start: "14:00", duration: 30 },
  ];
}

function StatusPill({ status }: { status: Application["status"] }) {
  const label: Record<string, string> = {
    submitted: "New", reviewed: "In review", shortlisted: "Shortlisted",
    interviewing: "Interviewing", offered: "Offered", hired: "Hired",
    rejected: "Rejected", withdrawn: "Withdrawn",
  };
  const tone = ["hired","offered"].includes(status) ? "border-cohere-green/30 bg-wash-green text-cohere-green"
             : ["rejected","withdrawn"].includes(status) ? "border-hairline bg-stone/40 text-slate-muted"
             : status === "submitted" ? "border-studio-maroon/30 bg-studio-maroon/[0.06] text-studio-maroon"
             : "border-cohere-blue/30 bg-wash-blue text-cohere-blue";
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-micro font-medium ${tone}`}>{label[status] ?? status}</span>;
}
