"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft, Calendar, Check, Clock, Loader2, MapPin, Video, X,
} from "lucide-react";

import {
  Application, InterviewSlot,
  acceptInterviewSlot, declineInterviewSlot,
  getMyApplication, listMyInterviews, withdrawApplication,
} from "@/lib/api/transactions";
import { PageHeader, MonoLabel, useToast, Confetti, Breadcrumb } from "@/components/ui";
import { fireOnce } from "@/lib/milestones";

export function ApplicationDetailClient({ token, applicationId }: { token: string; applicationId: string }) {
  const toast = useToast();
  const [app, setApp] = useState<Application | null>(null);
  const [slots, setSlots] = useState<InterviewSlot[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [celebrated, setCelebrated] = useState(false);

  async function refresh() {
    try {
      const [a, all] = await Promise.all([
        getMyApplication(token, applicationId),
        listMyInterviews(token),
      ]);
      setApp(a);
      setSlots(all.filter((s) => s.application_id === applicationId));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not load";
      setErr(msg);
    }
  }

  useEffect(() => { refresh(); }, [token, applicationId]);

  // Fire confetti + toast once per session when the applicant sees "hired" for the first time.
  useEffect(() => {
    if (!app || celebrated) return;
    if (app.status === "hired") {
      const key = `hire-celebrated-${app.id}`;
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, "1");
        setCelebrated(true);
        toast.success("You got the job. 🎉");
      }
    }
  }, [app, celebrated, toast]);

  // First-application milestone. Fires once ever per browser — landing on the
  // detail page for a fresh application is the closest single-place signal to
  // "you just applied", and it's guaranteed to run for anyone who submits
  // (ApplyFlow redirects here). Milestone id is browser-scoped, so a second
  // account on the same machine won't re-fire — that's the right tradeoff.
  useEffect(() => {
    if (!app || celebrated) return;
    if (app.days_since_submitted <= 0 && fireOnce("first_application_sent")) {
      setCelebrated(true);
      toast.success("🎉 First application sent! Employers usually reply within 3–5 days.");
    }
  }, [app, celebrated, toast]);

  async function accept(id: string) {
    setBusy(id);
    // Snapshot BEFORE mutating so we can roll back on server rejection.
    const prevSlots = slots;
    // Optimistic: mark accepted immediately in the UI so the confirm feels instant.
    setSlots((prev) => prev?.map((s) => s.id === id ? { ...s, status: "accepted" } : (s.status === "proposed" ? { ...s, status: "declined" } : s)) ?? prev);
    try {
      await acceptInterviewSlot(token, id);
      toast.success("Time booked. Employer notified.");
      await refresh();
    } catch (e: unknown) {
      // Roll back the optimistic mutation (item 18). If the server said the
      // slot is taken (409/400), surface the specific message so the user
      // knows to pick another; then refresh so the list reflects reality.
      setSlots(prevSlots ?? null);
      const errObj = e as { status?: number; message?: string } | Error;
      const status = (errObj as { status?: number }).status;
      const raw = e instanceof Error ? e.message : (errObj as { message?: string }).message ?? "Could not accept";
      const msg =
        status === 409 || status === 400 || /taken|already|conflict/i.test(raw)
          ? "This slot was already taken — pick another."
          : raw;
      toast.error(msg);
      await refresh();
    } finally { setBusy(null); }
  }

  async function decline(id: string) {
    setBusy(id);
    // Optimistic + undo
    const prevSlots = slots;
    setSlots((s) => s?.map((x) => x.id === id ? { ...x, status: "declined" } : x) ?? s);
    try {
      await declineInterviewSlot(token, id);
      toast.undo("Declined.", async () => {
        // Best-effort undo — re-accept if the server still allows.
        try { await acceptInterviewSlot(token, id); await refresh(); }
        catch { setSlots(prevSlots ?? null); }
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not decline";
      toast.error(msg);
      setSlots(prevSlots ?? null);
    } finally { setBusy(null); }
  }

  async function withdraw() {
    setBusy("withdraw");
    const prevApp = app;
    // Optimistic: flip status immediately.
    setApp((a) => a ? { ...a, status: "withdrawn" } : a);
    try {
      await withdrawApplication(token, applicationId);
      toast.undo("Withdrawn.", async () => {
        // No un-withdraw endpoint — best we can do is refresh from server, which will reflect any admin reversal.
        await refresh();
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not withdraw";
      toast.error(msg);
      setApp(prevApp ?? null);
    } finally { setBusy(null); }
  }

  const accepted = slots?.find((s) => s.status === "accepted");
  const proposed = slots?.filter((s) => s.status === "proposed") ?? [];

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[
          { label: "Applications", href: "/applicant/applications" },
          { label: app?.job_title ?? "Application" },
        ]} />

        {err && <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4">{err}</div>}
        {app === null && !err && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}

        {app && (
          <>
            <Confetti active={celebrated} />

            {app.status === "hired" && (
              <section className="rounded-xl border border-cohere-green/40 bg-wash-green p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
                <div className="mono-label text-cohere-green">Hired</div>
                <h2 className="mt-2 font-display text-heading text-cohere-ink">
                  You got it — {app.job_title} at {app.employer_name}.
                </h2>
                <p className="mt-3 text-body-lg text-slate">Three things to sort out before day one:</p>
                <ul className="mt-3 space-y-2 text-body text-cohere-ink">
                  <li className="flex items-start gap-2"><Check className="mt-0.5 h-4 w-4 text-cohere-green" strokeWidth={2}/>Confirm the start date and where to show up.</li>
                  <li className="flex items-start gap-2"><Check className="mt-0.5 h-4 w-4 text-cohere-green" strokeWidth={2}/>Bring physical copies of your credentials.</li>
                  <li className="flex items-start gap-2"><Check className="mt-0.5 h-4 w-4 text-cohere-green" strokeWidth={2}/>Save the manager's number in case something comes up.</li>
                </ul>
              </section>
            )}

            <PageHeader
              eyebrow={`Application, ${app.employer_name}`}
              title={app.job_title}
              lead={`Sent ${new Date(app.submitted_at).toLocaleDateString()}, ${app.days_since_submitted}d ago`}
              actions={
                ["submitted","reviewed","shortlisted"].includes(app.status) && (
                  <button onClick={withdraw} disabled={busy === "withdraw"} className="btn-pill-outline inline-flex items-center gap-1.5 border-studio-maroon text-studio-maroon">
                    {busy === "withdraw" ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
                    Withdraw
                  </button>
                )
              }
            />

            <Timeline app={app} />

            {/* Accepted interview */}
            {accepted && (
              <section className="rounded-xl border border-cohere-green/30 bg-wash-green p-5">
                <div className="flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-cohere-green" strokeWidth={1.75} />
                  <h2 className="font-display text-feature text-cohere-ink">Interview confirmed</h2>
                </div>
                <SlotBody slot={accepted} />
              </section>
            )}

            {/* Proposed interview slots */}
            {!accepted && proposed.length > 0 && (
              <section className="rounded-xl border border-cohere-blue/30 bg-wash-blue p-5">
                <div className="flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-cohere-blue" strokeWidth={1.75} />
                  <h2 className="font-display text-feature text-cohere-ink">Pick an interview time</h2>
                </div>
                <p className="mt-1 text-body text-slate">
                  {app.employer_name} sent {proposed.length} option{proposed.length === 1 ? "" : "s"}. Pick one and it goes on both your calendars.
                </p>
                <div className="mt-4 space-y-3">
                  {proposed.map((s) => (
                    <div key={s.id} className="rounded-lg border border-hairline bg-white p-4">
                      <SlotBody slot={s} />
                      <div className="mt-3 flex items-center justify-end gap-2">
                        <button onClick={() => decline(s.id)} disabled={busy === s.id} className="btn-pill-outline inline-flex items-center gap-1.5">
                          {busy === s.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
                          Not this one
                        </button>
                        <button onClick={() => accept(s.id)} disabled={busy === s.id} className="btn-primary-green inline-flex items-center gap-1.5">
                          {busy === s.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                          Book this time
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* What we sent */}
            <section className="rounded-xl border border-hairline bg-white p-5">
              <h2 className="font-display text-feature text-cohere-ink">What the employer saw</h2>
              <p className="mt-1 text-caption text-slate">Snapshot at the moment you applied — updates to your profile since then don't change this record.</p>

              {app.cover_note && (
                <div className="mt-4">
                  <MonoLabel className="mb-1.5 block">Your note</MonoLabel>
                  <p className="whitespace-pre-line text-body text-cohere-ink">{app.cover_note}</p>
                </div>
              )}

              {app.screening_answers.length > 0 && (
                <div className="mt-4">
                  <MonoLabel className="mb-2 block">Screening</MonoLabel>
                  <ul className="space-y-2">
                    {app.screening_answers.map((a, i) => (
                      <li key={i} className="rounded-md border border-hairline bg-stone/30 p-3">
                        <p className="text-caption font-medium text-cohere-ink">{a.prompt}</p>
                        <p className="mt-0.5 text-caption text-slate">
                          {a.answer}
                          {!a.knockout_pass && <span className="ml-2 text-studio-maroon">(flagged)</span>}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </main>
  );
}

function Timeline({ app }: { app: Application }) {
  const items = [
    { label: "Sent",         active: true, ts: app.submitted_at },
    { label: "Reviewed",     active: !!app.employer_viewed_at, ts: app.employer_viewed_at },
    { label: "Interviewing", active: ["interviewing","offered","hired"].includes(app.status), ts: null },
    { label: "Offered",      active: ["offered","hired"].includes(app.status), ts: null },
    { label: "Hired",        active: app.status === "hired", ts: null },
  ];
  return (
    <div className="rounded-xl border border-hairline bg-white p-5">
      <div className="flex items-center gap-0.5">
        {items.map((it, i) => (
          <div key={i} className="flex flex-1 items-center">
            <div className={`flex h-6 w-6 items-center justify-center rounded-full border ${it.active ? "border-cohere-green bg-cohere-green text-white" : "border-hairline bg-white text-slate-muted"}`}>
              {it.active ? <Check className="h-3 w-3" strokeWidth={2.5} /> : <Clock className="h-3 w-3" />}
            </div>
            {i < items.length - 1 && (
              <div className={`h-0.5 flex-1 ${it.active && items[i + 1].active ? "bg-cohere-green" : "bg-hairline"}`} />
            )}
          </div>
        ))}
      </div>
      <div className="mt-3 flex text-micro">
        {items.map((it, i) => (
          <div key={i} className={`flex-1 ${it.active ? "text-cohere-ink font-medium" : "text-slate-muted"}`}>
            {it.label}
            {it.ts && <div className="text-slate-muted">{new Date(it.ts).toLocaleDateString()}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

function SlotBody({ slot }: { slot: InterviewSlot }) {
  const start = new Date(slot.start_at);
  const end = new Date(slot.end_at);
  return (
    <div className="mt-2">
      <div className="text-body font-medium text-cohere-ink">
        {start.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}
        {", "}
        {start.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })} – {end.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-caption text-slate">
        {slot.location && <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />{slot.location}</span>}
        {slot.meeting_url && <a href={slot.meeting_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-cohere-blue underline"><Video className="h-3.5 w-3.5" />Meeting link</a>}
      </div>
      {slot.notes && <p className="mt-2 text-caption text-slate">{slot.notes}</p>}
    </div>
  );
}
