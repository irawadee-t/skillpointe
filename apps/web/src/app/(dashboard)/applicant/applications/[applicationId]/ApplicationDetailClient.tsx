"use client";

import { useEffect, useState } from "react";
import {
  Calendar, Check, Clock, Loader2, MapPin, UserRound, Video, X,
} from "lucide-react";

import {
  Application, InterviewSlot,
  acceptInterviewSlot, declineInterviewSlot,
  getMyApplication, listMyInterviews, withdrawApplication,
} from "@/lib/api/transactions";
import { useAutoRevalidate } from "@/hooks/useAutoRevalidate";
import { useViewAs, VIEW_AS_READONLY_TOOLTIP } from "@/hooks/useViewAs";
import { formatDate, formatDateShort } from "@/lib/format";
import { PageHeader, MonoLabel, useToast, Confetti, Breadcrumb } from "@/components/ui";
import { APPLICATION_STAGES, currentStageIndex } from "@/components/applications/stages";
import { browserTimeZoneLabel } from "@/components/interviews/SlotPickerGrid";
import { AddToCalendarButtons, CalendarEventInput } from "@/components/interviews/AddToCalendar";
import { fireOnce } from "@/lib/milestones";

export function ApplicationDetailClient({ token, applicationId }: { token: string; applicationId: string }) {
  const toast = useToast();
  const { isViewAs } = useViewAs();
  const [app, setApp] = useState<Application | null>(null);
  const [slots, setSlots] = useState<InterviewSlot[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [celebrated, setCelebrated] = useState(false);
  // Inline confirm for Withdraw — same pattern as credential delete.
  const [confirmingWithdraw, setConfirmingWithdraw] = useState(false);
  // Slot picker: tap to select, then confirm — plus a decline-all escape hatch.
  const [selectedSlotId, setSelectedSlotId] = useState<string | null>(null);
  const [decliningAll, setDecliningAll] = useState(false);
  const [declineReason, setDeclineReason] = useState("");

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

  // Keep the status timeline + slot list live: employer decisions and new
  // interview proposals appear without a manual reload (same pattern as the
  // DM thread). Paused while a mutation or the withdraw confirm is in flight
  // so a background refetch can't clobber optimistic state.
  useAutoRevalidate(refresh, {
    intervalMs: 30_000,
    enabled: busy === null && !confirmingWithdraw,
  });

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
      toast.success("First application sent. Employers usually reply within 3–5 days.");
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
          ? "This slot was already taken. Pick another."
          : raw;
      toast.error(msg);
      await refresh();
    } finally { setBusy(null); }
  }

  /** Decline every remaining proposed slot ("none of these work"). The API
   *  notifies the employer once — when the last proposed slot flips. */
  async function declineAll(reason: string) {
    setBusy("decline-all");
    const prevSlots = slots;
    const toDecline = (slots ?? []).filter((s) => s.status === "proposed");
    // Optimistic: flip them all immediately.
    setSlots((s) => s?.map((x) => x.status === "proposed" ? { ...x, status: "declined" } : x) ?? s);
    try {
      // Sequential so the server's "last one declined → notify employer"
      // logic sees a consistent count (and the reason rides on every call).
      for (const s of toDecline) {
        await declineInterviewSlot(token, s.id, reason.trim() || undefined);
      }
      toast.success("Declined. The employer has been notified.");
      setDecliningAll(false);
      setDeclineReason("");
      await refresh();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not decline";
      toast.error(msg);
      setSlots(prevSlots ?? null);
      await refresh();
    } finally { setBusy(null); }
  }

  async function withdraw() {
    const hadInterview = app?.status === "interviewing";
    setConfirmingWithdraw(false);
    setBusy("withdraw");
    const prevApp = app;
    // Optimistic: flip status immediately.
    setApp((a) => a ? { ...a, status: "withdrawn" } : a);
    try {
      await withdrawApplication(token, applicationId);
      // Honest confirmation — there is no un-withdraw endpoint, so no fake
      // Undo affordance. The one re-apply lives on the job page.
      toast.success(
        hadInterview
          ? "Withdrawn. Your interview was cancelled and the employer notified."
          : "Withdrawn. You can re-apply once from the job page.",
      );
      await refresh();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not withdraw";
      toast.error(msg);
      setApp(prevApp ?? null);
    } finally { setBusy(null); }
  }

  const accepted = slots?.find((s) => s.status === "accepted");
  const proposed = slots?.filter((s) => s.status === "proposed") ?? [];
  // Recently cancelled bookings (the API keeps them visible for 14 days) —
  // shown so a called-off interview reads as a cancellation, not a silent gap.
  const cancelled = slots?.filter((s) => s.status === "cancelled") ?? [];
  const withdrawWarnsInterview = app?.status === "interviewing";

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

            {/* Posting honesty: the job went inactive after this application.
                The timeline below stays intact — this is context, not an
                error, and terminal states don't need it. */}
            {app.job_active === false &&
              !["hired", "rejected", "withdrawn"].includes(app.status) && (
              <div className="rounded-[10px] border border-hairline bg-white px-5 py-3.5 text-body text-slate">
                <span className="font-medium text-cohere-ink">
                  This posting is no longer active.
                </span>{" "}
                Your application still stands. {app.employer_name} can see it
                and respond, but the job isn&apos;t accepting new applicants.
              </div>
            )}

            {app.status === "hired" && (
              <section className="rounded-xl border border-cohere-green/40 bg-wash-green p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
                <div className="mono-label text-cohere-green">Hired</div>
                <h2 className="mt-2 font-display text-heading text-cohere-ink">
                  You got it: {app.job_title} at {app.employer_name}.
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
              lead={`Sent ${formatDate(app.submitted_at)}, ${app.days_since_submitted}d ago`}
              actions={
                ["submitted","reviewed","shortlisted","interviewing"].includes(app.status) && (
                  confirmingWithdraw ? (
                    // Inline confirm — same pattern as credential delete.
                    // Withdrawing from the interviewing stage also cancels the
                    // interview, so the confirm says so up front.
                    <span className="flex items-center gap-2">
                      <span className="text-caption text-slate">
                        {withdrawWarnsInterview
                          ? "Withdraw? Your interview will be cancelled and the employer notified."
                          : "Withdraw application?"}
                      </span>
                      <button
                        onClick={withdraw}
                        disabled={busy === "withdraw" || isViewAs} title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
                        className="rounded-pill bg-error-red px-3 py-1.5 text-micro font-medium text-white hover:opacity-90"
                      >
                        {busy === "withdraw" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Yes, withdraw"}
                      </button>
                      <button
                        onClick={() => setConfirmingWithdraw(false)}
                        disabled={busy === "withdraw" || isViewAs} title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
                        className="text-micro text-slate hover:text-ink"
                      >
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <button
                      onClick={() => setConfirmingWithdraw(true)}
                      disabled={busy === "withdraw" || isViewAs} title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
                      className="btn-pill-outline inline-flex items-center gap-1.5 border-studio-maroon text-studio-maroon"
                    >
                      {busy === "withdraw" ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
                      Withdraw
                    </button>
                  )
                )
              }
            />

            <Timeline app={app} />

            {/* Accepted interview */}
            {accepted && (
              <section className="rounded-xl border border-cohere-green/30 bg-wash-green p-5">
                <div className="flex items-center gap-2">
                  <Calendar className="h-5 w-5 text-cohere-green" strokeWidth={1.75} />
                  <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Interview confirmed</h2>
                </div>
                <SlotBody slot={accepted} />
                <AddToCalendarButtons
                  event={interviewEvent(accepted, app)}
                  className="mt-4 border-t border-cohere-green/20 pt-3"
                />
              </section>
            )}

            {/* A booked interview that was called off — honest state, not a
                silent gap. Hidden once new times arrive or the application
                reaches a terminal stage. */}
            {!accepted && proposed.length === 0 && cancelled.length > 0 &&
              !["hired", "rejected", "withdrawn"].includes(app.status) && (
              <section className="rounded-[10px] border border-hairline bg-white p-6">
                <div className="flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-slate" strokeWidth={1.75} />
                  <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Interview cancelled</h2>
                </div>
                <p className="mt-1 text-body text-slate">
                  {app.employer_name || "The employer"} cancelled the{" "}
                  {new Date(cancelled[cancelled.length - 1].start_at).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
                  {" "}
                  {new Date(cancelled[cancelled.length - 1].start_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
                  {" "}interview. Your application is still open. If they propose new times, they will show up here.
                </p>
              </section>
            )}

            {/* Proposed interview slots — tap one, then confirm */}
            {!accepted && proposed.length > 0 && (() => {
              const now = new Date();
              const selectable = proposed.filter((s) => new Date(s.start_at) > now);
              const selected = selectable.find((s) => s.id === selectedSlotId) ?? null;
              return (
                <section className="rounded-[10px] border border-hairline bg-white p-6">
                  <div className="flex items-center gap-2">
                    <Calendar className="h-4 w-4 text-cohere-ink" strokeWidth={1.75} />
                    <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Pick a time that works</h2>
                  </div>
                  <p className="mt-1 text-body text-slate">
                    {app.employer_name} sent {proposed.length} option{proposed.length === 1 ? "" : "s"}. Pick one and it locks in for both of you.
                  </p>

                  <div role="radiogroup" aria-label="Proposed interview times" className="mt-4 grid gap-2 sm:grid-cols-2">
                    {proposed.map((s) => {
                      const past = new Date(s.start_at) <= now;
                      const isSelected = s.id === selectedSlotId && !past;
                      const start = new Date(s.start_at);
                      const mins = Math.round((new Date(s.end_at).getTime() - start.getTime()) / 60_000);
                      return (
                        <button
                          key={s.id}
                          type="button"
                          role="radio"
                          aria-checked={isSelected}
                          aria-disabled={past || undefined}
                          disabled={isViewAs}
                          title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
                          onClick={() => { if (!past) setSelectedSlotId(isSelected ? null : s.id); }}
                          className={[
                            "rounded-[8px] border p-3.5 text-left",
                            "transition-[border-color,background-color,transform] duration-150 ease-out motion-reduce:transition-none",
                            past
                              ? "cursor-default border-hairline bg-stone/30"
                              : isSelected
                                ? "border-cohere-ink bg-ink text-white active:scale-[0.99] motion-reduce:active:scale-100"
                                : "border-hairline bg-white hover:border-slate active:scale-[0.99] motion-reduce:active:scale-100",
                          ].join(" ")}
                        >
                          <div className={`text-body font-medium tabular-nums ${past ? "text-slate-muted" : isSelected ? "text-white" : "text-cohere-ink"}`}>
                            {start.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
                            {" · "}
                            {start.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
                          </div>
                          <div className={`mt-0.5 text-caption ${past ? "text-slate-muted" : isSelected ? "text-white/70" : "text-slate"}`}>
                            {past ? "This time has passed" : `${mins} min`}
                            {!past && s.location && <> · <MapPin className="mb-0.5 inline h-3 w-3" /> {s.location}</>}
                            {!past && s.meeting_url && <> · <Video className="mb-0.5 inline h-3 w-3" /> Video call</>}
                          </div>
                        </button>
                      );
                    })}
                  </div>

                  {proposed[0] && interviewerLine(proposed[0]) && (
                    <p className="mt-3 inline-flex items-center gap-1.5 text-caption text-cohere-ink">
                      <UserRound className="h-3.5 w-3.5 text-slate" />
                      You&rsquo;ll meet: <span className="font-medium">{interviewerLine(proposed[0])}</span>
                    </p>
                  )}
                  {proposed[0]?.notes && (
                    <p className="mt-3 text-caption text-slate">From {app.employer_name}: {proposed[0].notes}</p>
                  )}
                  <p className="mt-2 text-micro text-slate-muted">Times shown in {browserTimeZoneLabel()}.</p>

                  {selectable.length === 0 && (
                    <p className="mt-3 text-caption text-slate">
                      All the proposed times have passed. Let the employer know so they can send new ones.
                    </p>
                  )}

                  {/* Confirm + decline-all footer */}
                  {!decliningAll ? (
                    <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
                      <button
                        onClick={() => setDecliningAll(true)}
                        disabled={busy !== null || isViewAs}
                        title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
                        className="btn-pill-outline inline-flex items-center gap-1.5"
                      >
                        <X className="h-4 w-4" /> None of these work
                      </button>
                      <button
                        onClick={() => selected && accept(selected.id)}
                        disabled={!selected || busy !== null || isViewAs}
                        title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
                        className="btn-primary-green inline-flex items-center gap-1.5 disabled:opacity-50"
                      >
                        {busy !== null && busy !== "decline-all" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                        {selected
                          ? `Book ${new Date(selected.start_at).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })} · ${new Date(selected.start_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`
                          : "Pick a time to book"}
                      </button>
                    </div>
                  ) : (
                    <div className="mt-4 rounded-[8px] border border-hairline bg-stone/30 p-4">
                      <MonoLabel className="mb-1 block">Why don&apos;t these work? (optional)</MonoLabel>
                      <textarea
                        value={declineReason}
                        onChange={(e) => setDeclineReason(e.target.value)}
                        rows={2}
                        maxLength={500}
                        placeholder="e.g. I'm in class weekday mornings. Afternoons are better."
                        className="input-cohere text-caption resize-y"
                      />
                      <div className="mt-3 flex items-center justify-end gap-2">
                        <button onClick={() => { setDecliningAll(false); setDeclineReason(""); }} disabled={busy === "decline-all"} className="text-caption text-slate hover:text-cohere-ink">
                          Cancel
                        </button>
                        <button
                          onClick={() => declineAll(declineReason)}
                          disabled={busy === "decline-all" || isViewAs}
                          title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
                          className="btn-pill-outline inline-flex items-center gap-1.5 border-studio-maroon text-studio-maroon"
                        >
                          {busy === "decline-all" ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
                          Decline all {proposed.length} time{proposed.length === 1 ? "" : "s"}
                        </button>
                      </div>
                    </div>
                  )}
                </section>
              );
            })()}

            {/* What we sent */}
            <section className="rounded-xl border border-hairline bg-white p-5">
              <h2 className="text-[1.0625rem] font-medium text-cohere-ink">What the employer saw</h2>
              <p className="mt-1 text-caption text-slate">Snapshot at the moment you applied. Updates to your profile since then don't change this record.</p>

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
  // Rendered from the shared canonical stage model (stages.ts) so the list and
  // detail views always show the same stages — same names, count, and order.
  const activeIx = currentStageIndex(app.status, app.employer_viewed_at);
  const items = APPLICATION_STAGES.map((s, i) => ({
    label: s.label,
    active: activeIx >= i,
    ts: s.key === "submitted"
      ? app.submitted_at
      : s.key === "reviewed"
        ? app.employer_viewed_at
        : null,
  }));
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
            {it.ts && <div className="text-slate-muted">{formatDateShort(it.ts)}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Add to calendar — shared trio (Google / Outlook / .ics) ─────────────── */

/** "Marcus Lee, Production Supervisor" (or null when no assignee is set). */
export function interviewerLine(slot: InterviewSlot): string | null {
  const name = (slot.interviewer_name ?? "").trim();
  if (!name) return null;
  const title = (slot.interviewer_title ?? "").trim();
  return title ? `${name}, ${title}` : name;
}

function interviewEvent(slot: InterviewSlot, app: Application): CalendarEventInput {
  const who = interviewerLine(slot);
  const detailBits = [
    app.employer_name ? `Interview with ${app.employer_name}.` : "Interview.",
    who ? `You'll meet ${who}.` : null,
    slot.meeting_url ? `Join: ${slot.meeting_url}` : null,
    slot.notes || null,
  ].filter(Boolean) as string[];
  return {
    slotId: slot.id,
    title: `Interview: ${app.job_title}${app.employer_name ? ` at ${app.employer_name}` : ""}`,
    description: detailBits.join("\n"),
    location: slot.location,
    meetingUrl: slot.meeting_url,
    startAt: slot.start_at,
    endAt: slot.end_at,
  };
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
      {interviewerLine(slot) && (
        <p className="mt-2 inline-flex items-center gap-1.5 text-caption text-cohere-ink">
          <UserRound className="h-3.5 w-3.5 text-slate" />
          You&rsquo;ll meet: <span className="font-medium">{interviewerLine(slot)}</span>
        </p>
      )}
      {slot.notes && <p className="mt-2 text-caption text-slate">{slot.notes}</p>}
    </div>
  );
}
