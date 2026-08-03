"use client";

import { useEffect, useState } from "react";
import {
  Calendar, Check, Loader2, MapPin, ShieldAlert, UserRound, Video, X, Send,
} from "lucide-react";

import {
  Application, InterviewSlot, InterviewerAssignment, TeamContact,
  cancelInterviewSlot,
  getEmployerApplication, getEmployerApplicationSlots, getEmployerTeam,
  patchEmployerApplication, proposeInterviewSlots,
  revertEmployerApplication,
} from "@/lib/api/transactions";
import {
  SchedulingRequest,
  cancelSchedulingRequest, createSchedulingRequest, getSchedulingRequestForApplication,
} from "@/lib/api/team";
import { formatRelative } from "@/lib/time";
import { useAutoRevalidate } from "@/hooks/useAutoRevalidate";
import {
  PageHeader, MonoLabel, CopyableText, Breadcrumb, useToast,
  CREDENTIAL_CHIP_CLASS, STATUS_CHIP_BASE, STATUS_TONE_CLASSES,
  VERIFICATION_LEVEL_META, statusChipClass,
} from "@/components/ui";
import { BadgeCheck } from "lucide-react";
import { formatDateShort } from "@/lib/format";
import { ApplicationStatusChip } from "@/components/applications/ApplicationStatusChip";
import { JobPreviewTrigger } from "@/components/jobs/JobPreviewDialog";
import { SlotPickerGrid, PickedSlot, browserTimeZoneLabel } from "@/components/interviews/SlotPickerGrid";
import { AddToCalendarButtons, CalendarEventInput } from "@/components/interviews/AddToCalendar";

/**
 * Employer's application detail — snapshot review, status transitions,
 * and the when2meet-style interview slot picker (up to 5 times).
 *
 * `readOnly` = admin viewing an employer page: everything renders, but the
 * employer actions (status changes, proposing times) are hidden — admin must
 * not act on behalf of employers.
 */
export function EmployerApplicationDetailClient({
  token, applicationId, readOnly = false,
}: { token: string; applicationId: string; readOnly?: boolean }) {
  const toast = useToast();
  const [app, setApp] = useState<Application | null>(null);
  const [slots, setSlots] = useState<InterviewSlot[] | null>(null);
  // Pending "let them pick the times" delegation for this application (null
  // when none). Drives the waiting/assigned banners below.
  const [schedReq, setSchedReq] = useState<SchedulingRequest | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [proposing, setProposing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  // Inline confirmation (replaces native confirm()) for knockout-flagged actions.
  const [pendingConfirm, setPendingConfirm] = useState<{ message: string; onConfirm: () => void } | null>(null);
  // Inline decision confirm — Reject shows (and lets the employer edit) the
  // decision note before it's attached; Mark hired confirms in plain words.
  const [pendingDecision, setPendingDecision] = useState<
    | { status: "rejected"; note: string }
    | { status: "hired" }
    | null
  >(null);
  // The "Cancel interview" inline confirm on the confirmed card — tracked
  // here so the background refresh pauses while it's open.
  const [cancelOpen, setCancelOpen] = useState(false);

  async function load(opts?: { announceAutoReview?: boolean }) {
    try {
      const [a, s, sr] = await Promise.all([
        getEmployerApplication(token, applicationId),
        getEmployerApplicationSlots(token, applicationId).catch(() => null),
        // Admin (read-only) has no employer link — treat errors as "none".
        getSchedulingRequestForApplication(token, applicationId).catch(() => null),
      ]);
      setApp(a);
      setSlots(s);
      setSchedReq(sr);
      // Opening a New application auto-transitions it to In review on the
      // backend. Announce that the first time it happens (viewed just now).
      if (
        opts?.announceAutoReview &&
        a.status === "reviewed" &&
        a.employer_viewed_at &&
        Date.now() - new Date(a.employer_viewed_at).getTime() < 15_000
      ) {
        toast.info("Moved to In review. Opening a new application marks it as seen.");
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not load");
    }
  }
  useEffect(() => { load({ announceAutoReview: true }); }, [token, applicationId]);

  // Withdrawals, interview accepts/declines, and other applicant-side changes
  // appear without a manual reload (same 30s pattern as the applicant side).
  // Paused while any mutation, confirm, or panel is in flight so a background
  // refetch can't clobber in-progress state.
  useAutoRevalidate(load, {
    intervalMs: 30_000,
    enabled:
      busy === null && !proposing && !pendingConfirm && !pendingDecision && !cancelOpen,
  });

  function knockoutPrompt(): string | null {
    if (!app) return null;
    const failed = app.screening_answers.filter((a) => a.knockout_pass === false);
    if (failed.length === 0) return null;
    const which = failed.map((a) => `"${a.prompt}"`).join(", ");
    return `This candidate flagged ${which} screening question. Continue anyway?`;
  }

  async function setStatus(status: string, note?: string, skipGuard = false) {
    // Guard destructive-forward actions if knockout screening flagged.
    // (hired is guarded inside its own decision confirm panel instead.)
    if (!skipGuard && status === "shortlisted") {
      const prompt = knockoutPrompt();
      if (prompt) {
        setPendingConfirm({
          message: prompt,
          onConfirm: () => { setPendingConfirm(null); setStatus(status, note, true); },
        });
        return;
      }
    }
    setBusy(status);
    try {
      const next = await patchEmployerApplication(token, applicationId, { status, decision_note: note });
      setApp(next);
      setPendingDecision(null);
      // REAL undo: the toast's Undo calls the revert endpoint (which restores
      // the previous stage, clears decision state, and voids a hire outcome).
      // Never a fake undo — if the revert fails, we say so and roll back.
      if (status === "shortlisted" || status === "rejected" || status === "hired") {
        const msg =
          status === "shortlisted" ? "Shortlisted" :
          status === "rejected" ? "Application rejected" :
          "Marked hired. Recorded in your analytics";
        toast.undo(msg, () => doRevert(next));
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not update");
    } finally { setBusy(null); }
  }

  /**
   * Revert the last decision via POST …/revert. Optimistic: the UI drops back
   * a stage immediately and rolls back to the server truth on failure.
   * `fromApp` is the state to restore if the revert fails.
   */
  async function doRevert(fromApp: Application) {
    setBusy("revert");
    // Optimistic: we don't know the exact previous stage client-side, so show
    // the safe fallback the backend also uses ("reviewed") until it answers.
    setApp((cur) => (cur ? { ...cur, status: "reviewed" } : cur));
    try {
      const reverted = await revertEmployerApplication(token, applicationId);
      setApp(reverted);
      toast.success("Decision reverted");
    } catch (e: unknown) {
      setApp(fromApp); // rollback — the revert did NOT happen
      toast.error(e instanceof Error ? e.message : "Could not revert");
    } finally { setBusy(null); }
  }

  function startProposing() {
    const prompt = knockoutPrompt();
    if (prompt) {
      setPendingConfirm({
        message: prompt,
        onConfirm: () => { setPendingConfirm(null); setProposing((v) => !v); },
      });
      return;
    }
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

        {pendingConfirm && (
          <div role="alertdialog" aria-label="Confirm action" className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4">
            <p className="text-body text-cohere-ink">{pendingConfirm.message}</p>
            <div className="mt-3 flex items-center gap-2">
              <button onClick={pendingConfirm.onConfirm} className="btn-primary inline-flex items-center gap-1.5">
                Continue anyway
              </button>
              <button onClick={() => setPendingConfirm(null)} className="btn-pill-outline">
                Cancel
              </button>
            </div>
          </div>
        )}
        {app === null && !err && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}

        {app && (
          <>
            {/* The candidate is the subject of this page — their name is the
                H1; the job is the context line above it. */}
            <PageHeader
              eyebrow={
                <>
                  {/* The job title opens the job-description popup */}
                  Application for{" "}
                  <JobPreviewTrigger
                    jobId={app.job_id}
                    jobTitle={app.job_title}
                    meta={app.employer_name}
                    token={token}
                    variant="link"
                    label={app.job_title}
                  />
                  {" · "}
                  {formatDateShort(app.submitted_at)}
                </>
              }
              title={app.applicant_name || "Applicant"}
              lead={app.knockout_failed
                ? "One of this applicant's screening answers didn't match a hard requirement. Worth a careful read."
                : "Read the snapshot, then move them forward or propose interview times."}
              actions={<ApplicationStatusChip status={app.status} viewer="employer" />}
            />

            {app.knockout_failed && (
              <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4 text-body text-cohere-ink">
                <ShieldAlert className="mr-1 inline h-4 w-4 text-studio-maroon" />
                Screening flag: see the applicant's answers below.
              </div>
            )}

            {/* Action toolbar — hidden for admin (read-only view) */}
            {!readOnly && (
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
                  <button
                    onClick={() => setPendingDecision({ status: "hired" })}
                    disabled={busy === "hired"}
                    className="btn-primary-green inline-flex items-center gap-1.5"
                  >
                    {busy === "hired" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                    Mark hired
                  </button>
                )}
                {!["hired","rejected","withdrawn"].includes(app.status) && (
                  <button
                    onClick={() => setPendingDecision({ status: "rejected", note: "Not a match for this role right now." })}
                    disabled={busy === "rejected"}
                    className="btn-pill-outline inline-flex items-center gap-1.5 border-studio-maroon text-studio-maroon"
                  >
                    {busy === "rejected" ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
                    Reject
                  </button>
                )}

                {/* Quiet revert affordances — decisions stay reversible after
                    the toast window closes. Shortlist/reject revert directly;
                    undoing a hire gets its own confirm because it also voids
                    the recorded hire outcome in analytics. */}
                {(app.status === "shortlisted" || app.status === "rejected") && (
                  <button
                    onClick={() => app && doRevert(app)}
                    disabled={busy !== null}
                    className="inline-flex items-center gap-1.5 self-center text-caption text-slate underline underline-offset-2 transition-colors hover:text-cohere-ink disabled:opacity-50"
                  >
                    {busy === "revert" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {app.status === "rejected" ? "Reopen and revert to In review" : "Revert to In review"}
                  </button>
                )}
                {app.status === "hired" && (
                  <button
                    onClick={() => {
                      const current = app;
                      setPendingConfirm({
                        message:
                          "Undo this hire? The application returns to its previous stage and the hire is removed from your analytics.",
                        onConfirm: () => { setPendingConfirm(null); doRevert(current); },
                      });
                    }}
                    disabled={busy !== null}
                    className="inline-flex items-center gap-1.5 self-center text-caption text-slate underline underline-offset-2 transition-colors hover:text-cohere-ink disabled:opacity-50"
                  >
                    {busy === "revert" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Undo hire
                  </button>
                )}
              </div>
            )}

            {/* Inline decision confirm — no hidden canned notes, no silent
                one-click terminal actions. */}
            {pendingDecision && !readOnly && (
              <div role="alertdialog" aria-label="Confirm decision" className="rounded-xl border border-hairline bg-white p-5">
                {pendingDecision.status === "hired" ? (
                  <>
                    <p className="text-body font-medium text-cohere-ink">
                      Report {app.applicant_name || "this applicant"} as hired for {app.job_title}?
                    </p>
                    <p className="mt-1 text-caption text-slate">
                      This marks the application Hired and records the hire in your analytics.
                    </p>
                    {knockoutPrompt() && (
                      <p className="mt-2 text-caption text-studio-maroon">
                        <ShieldAlert className="mr-1 inline h-3.5 w-3.5" />
                        {knockoutPrompt()}
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <p className="text-body font-medium text-cohere-ink">
                      Reject {app.applicant_name || "this applicant"} for {app.job_title}?
                    </p>
                    <label className="mt-3 block">
                      <MonoLabel className="mb-1 block">Decision note (saved with the rejection)</MonoLabel>
                      <textarea
                        value={pendingDecision.note}
                        onChange={(e) => setPendingDecision({ status: "rejected", note: e.target.value })}
                        rows={2}
                        className="input-cohere text-caption resize-y"
                      />
                    </label>
                  </>
                )}
                <div className="mt-3 flex items-center gap-2">
                  <button
                    onClick={() =>
                      pendingDecision.status === "hired"
                        ? setStatus("hired", undefined, true)
                        : setStatus("rejected", pendingDecision.note.trim() || undefined, true)
                    }
                    disabled={busy !== null}
                    className={`inline-flex items-center gap-1.5 ${pendingDecision.status === "hired" ? "btn-primary-green" : "btn-primary"}`}
                  >
                    {busy !== null ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                    {pendingDecision.status === "hired" ? "Confirm hire" : "Confirm rejection"}
                  </button>
                  <button onClick={() => setPendingDecision(null)} className="btn-pill-outline">
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Delegated scheduling state — who's picking the times */}
            {schedReq && !readOnly && !proposing && (
              schedReq.assigned_to_me ? (
                <div className="rounded-[10px] border border-hairline bg-white p-5">
                  <p className="text-body font-medium text-cohere-ink">
                    <Calendar className="mr-1.5 inline h-4 w-4" />
                    {schedReq.requester_name || "A teammate"} asked you to propose the interview times
                  </p>
                  <p className="mt-1 text-caption text-slate">
                    You&apos;re running this interview — pick 3-5 times that work for you and the
                    applicant chooses one.
                    {schedReq.note && <> Note: &ldquo;{schedReq.note}&rdquo;</>}
                  </p>
                  <button
                    onClick={startProposing}
                    className="btn-primary mt-3 inline-flex items-center gap-1.5"
                  >
                    <Calendar className="h-4 w-4" /> Propose times
                  </button>
                </div>
              ) : (
                <div className="rounded-[10px] border border-hairline bg-white p-5">
                  <p className="text-body font-medium text-cohere-ink">
                    Waiting on {schedReq.assignee_name || "a teammate"} to propose times
                  </p>
                  <p className="mt-1 text-caption text-slate">
                    {schedReq.requested_by_me ? "You asked them" : `${schedReq.requester_name || "A teammate"} asked them`}{" "}
                    {formatRelative(schedReq.created_at)} — they&apos;ve been notified in-app and by
                    email. If you propose times yourself, this request closes automatically.
                  </p>
                  {schedReq.requested_by_me && (
                    <button
                      onClick={async () => {
                        setBusy("cancel-sched");
                        try {
                          await cancelSchedulingRequest(token, schedReq.id);
                          toast.info(`${schedReq.assignee_name || "Your teammate"} was told it's no longer needed.`);
                          await load();
                        } catch (e: unknown) {
                          toast.error(e instanceof Error ? e.message : "Could not cancel the request.");
                        } finally { setBusy(null); }
                      }}
                      disabled={busy !== null}
                      className="mt-2 inline-flex items-center gap-1.5 text-caption text-slate underline underline-offset-2 transition-colors hover:text-cohere-ink disabled:opacity-50"
                    >
                      {busy === "cancel-sched" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      Cancel request
                    </button>
                  )}
                </div>
              )
            )}

            {proposing && !readOnly && (
              <ProposeInterviewPanel
                token={token}
                applicationId={applicationId}
                supersedeCount={slots?.filter((s) => s.status === "proposed").length ?? 0}
                pendingRequest={schedReq}
                onDone={() => { setProposing(false); load(); }}
              />
            )}

            {/* Where scheduling stands — confirmed time, pending proposals, declines */}
            {slots && (
              <InterviewStatusSection
                slots={slots}
                proposing={proposing}
                app={app}
                token={token}
                readOnly={readOnly}
                onChanged={() => load()}
                onCancelOpenChange={setCancelOpen}
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

const SHARED_FIELD_LABELS: Record<string, string> = {
  contact: "contact info",
  location: "location",
  program: "program or trade",
  availability: "availability",
  credentials: "credentials",
  resume: "resume",
};

/** One deduped credential row for the snapshot: name + best verification level. */
interface SnapshotCredential {
  name: string;
  level: number;
}

/**
 * Dedupe snapshot credentials by name (case-insensitive), keeping the highest
 * verification level seen. Reads the richer `certifications_detail` shape when
 * the snapshot has it, and falls back to the legacy plain-string list
 * (level 0 = self-reported) for older applications.
 */
function snapshotCredentials(snap: Record<string, unknown>): SnapshotCredential[] {
  const detail = snap.certifications_detail as Array<{ name?: unknown; verification_level?: unknown }> | undefined;
  const raw: SnapshotCredential[] = Array.isArray(detail)
    ? detail
        .filter((c) => typeof c?.name === "string" && (c.name as string).trim())
        .map((c) => ({ name: (c.name as string).trim(), level: typeof c.verification_level === "number" ? c.verification_level : 0 }))
    : ((snap.certifications as string[] | undefined) ?? [])
        .filter((c) => typeof c === "string" && c.trim())
        .map((c) => ({ name: c.trim(), level: 0 }));
  const byName = new Map<string, SnapshotCredential>();
  for (const c of raw) {
    const key = c.name.toLowerCase();
    const prev = byName.get(key);
    if (!prev || c.level > prev.level) byName.set(key, { name: prev?.name ?? c.name, level: Math.max(c.level, prev?.level ?? 0) });
  }
  return [...byName.values()];
}

function ApplicantSnapshot({ app }: { app: Application }) {
  const snap = app.resume_snapshot as Record<string, unknown>;
  const skills = (snap.skills as string[] | undefined) ?? [];
  const certs = snapshotCredentials(snap);
  const sharedFields = (snap.shared_fields as string[] | undefined) ?? [];
  const availability =
    (snap.available_from_date as string | undefined)
      ? `Available from ${snap.available_from_date}`
      : (snap.expected_completion_date as string | undefined)
        ? `Program ends ${snap.expected_completion_date}`
        : undefined;
  return (
    <section className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
      <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Applicant snapshot</h2>
      <p className="mt-1 text-caption text-slate">
        Captured when they applied. Any profile changes since then aren&apos;t shown here.
        {sharedFields.length > 0 && (
          <> Shared with their consent: {sharedFields.map((f) => SHARED_FIELD_LABELS[f] ?? f).join(", ")}.</>
        )}
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Name"     value={`${snap.first_name || ""} ${snap.last_name || ""}`.trim()} />
        <Field label="Location" value={[snap.city, snap.state].filter(Boolean).join(", ")} />
        <FieldCopy label="Phone" value={snap.phone as string | undefined} />
        <FieldCopy label="Email" value={snap.email as string | undefined} />
        <Field label="Trade / program" value={snap.program_name_raw as string | undefined} />
        <Field label="Years experience" value={snap.years_experience ? String(snap.years_experience) : undefined} />
        <Field label="Availability" value={availability} />
        <Field label="Resume" value={snap.resume_filename as string | undefined} />
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
                {certs.map((c) => {
                  const meta = VERIFICATION_LEVEL_META[c.level];
                  return (
                    <span key={c.name} className="inline-flex items-center gap-1">
                      <span className={CREDENTIAL_CHIP_CLASS}>{c.name}</span>
                      {/* Verification affix — trust semantics on the decision
                          surface (statusTones VERIFICATION_LEVEL_META). */}
                      {c.level >= 1 && meta && (
                        <span className={statusChipClass(meta.tone)}>
                          <BadgeCheck className="h-3 w-3" aria-hidden="true" /> {meta.label}
                        </span>
                      )}
                    </span>
                  );
                })}
              </div>
            </div>
          )}
          {skills.length > 0 && (
            <div>
              <MonoLabel className="mb-1.5 block">Skills</MonoLabel>
              <div className="flex flex-wrap gap-1.5">
                {skills.map((s) => <span key={s} className={`${STATUS_CHIP_BASE} ${STATUS_TONE_CLASSES.neutral}`}>{s}</span>)}
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
// Interview proposal panel — when2meet-style week grid, up to 5 times
// ---------------------------------------------------------------------------

type InterviewerMode = "me" | "team" | "other";

function ProposeInterviewPanel({
  token, applicationId, supersedeCount, pendingRequest, onDone,
}: {
  token: string; applicationId: string; supersedeCount: number;
  /** Pending "let them pick the times" request for this application, if any. */
  pendingRequest?: SchedulingRequest | null;
  onDone: () => void;
}) {
  const [picked, setPicked] = useState<PickedSlot[]>([]);
  const [location, setLocation] = useState("");
  const [meetingUrl, setMeetingUrl] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Who's running this interview? Default "Me" — the logged-in contact.
  const [mode, setMode] = useState<InterviewerMode>("me");
  const [team, setTeam] = useState<TeamContact[] | null>(null);
  const [teamContactId, setTeamContactId] = useState("");
  const [interviewerName, setInterviewerName] = useState("");
  const [interviewerEmail, setInterviewerEmail] = useState("");
  const [interviewerTitle, setInterviewerTitle] = useState("");
  // "Let them pick the times" — instead of painting the grid on the
  // teammate's behalf, send them a scheduling request.
  const [delegate, setDelegate] = useState(false);
  const [delegationNote, setDelegationNote] = useState("");

  useEffect(() => {
    getEmployerTeam(token).then(setTeam).catch(() => setTeam([]));
  }, [token]);

  const me = team?.find((t) => t.is_me) ?? null;
  const teammates = (team ?? []).filter((t) => !t.is_me);

  // When I'm fulfilling a scheduling request, I AM the interviewer — the
  // assignment is locked to me (the originator chose me on purpose).
  const fulfilling = pendingRequest?.assigned_to_me ?? false;
  const delegating = mode === "team" && delegate && !fulfilling;
  const chosenTeammate = teammates.find((t) => t.contact_id === teamContactId) ?? null;
  const teammateLabel = (t: TeamContact) => t.name || t.email;

  function interviewerPayload(): InterviewerAssignment | undefined {
    if (mode === "me") {
      // Explicitly pin my own contact; a typed name personalizes the line the
      // applicant sees ("You'll meet …" falls back to nothing if left blank).
      return {
        ...(me ? { contact_id: me.contact_id } : {}),
        ...(interviewerName.trim() ? { name: interviewerName.trim() } : {}),
      };
    }
    if (mode === "team") {
      if (!teamContactId) return undefined;
      return {
        contact_id: teamContactId,
        ...(interviewerName.trim() ? { name: interviewerName.trim() } : {}),
        ...(interviewerTitle.trim() ? { title: interviewerTitle.trim() } : {}),
      };
    }
    return {
      ...(interviewerName.trim() ? { name: interviewerName.trim() } : {}),
      ...(interviewerEmail.trim() ? { email: interviewerEmail.trim() } : {}),
      ...(interviewerTitle.trim() ? { title: interviewerTitle.trim() } : {}),
    };
  }

  async function submit() {
    if (delegating) {
      if (!teamContactId) { setErr("Pick which teammate should choose the times."); return; }
      setBusy(true); setErr(null);
      try {
        await createSchedulingRequest(token, applicationId, {
          assignee_contact_id: teamContactId,
          ...(delegationNote.trim() ? { note: delegationNote.trim() } : {}),
        });
        onDone();
      } catch (e: unknown) {
        setErr(e instanceof Error ? e.message : "Could not send the scheduling request.");
      } finally { setBusy(false); }
      return;
    }
    if (picked.length === 0) { setErr("Pick at least one time on the grid."); return; }
    if (mode === "team" && !teamContactId) { setErr("Pick which teammate runs the interview (or switch back to Me)."); return; }
    if (mode === "other" && !interviewerName.trim()) { setErr("Add the interviewer's name so the applicant knows who they'll meet."); return; }
    setBusy(true); setErr(null);
    try {
      const slots = picked.map((p) => ({
        start_at: p.start.toISOString(),
        end_at: new Date(p.start.getTime() + p.durationMin * 60_000).toISOString(),
        location: location.trim() || undefined,
        meeting_url: meetingUrl.trim() || undefined,
        notes: notes.trim() || undefined,
      }));
      await proposeInterviewSlots(token, applicationId, slots, interviewerPayload());
      onDone();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not propose");
    } finally { setBusy(false); }
  }

  return (
    <section className="rounded-[10px] border border-hairline bg-white p-6">
      <div className="flex items-center gap-2">
        <Calendar className="h-4 w-4 text-cohere-ink" strokeWidth={1.75} />
        <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Propose interview times</h2>
      </div>
      <p className="mt-1 text-body text-slate">
        {delegating
          ? "Hand the time-picking to the teammate who's running the interview — they choose the times on their own calendar."
          : "Offer up to five times. The applicant picks one and both sides see the confirmed time."}
        {!delegating && supersedeCount > 0 && (
          <> Sending replaces the {supersedeCount} time{supersedeCount === 1 ? "" : "s"} currently waiting on the applicant.</>
        )}
      </p>

      {err && <p className="mt-3 text-caption text-studio-maroon" role="alert">{err}</p>}

      {!delegating && (
        <div className="mt-4">
          <SlotPickerGrid slots={picked} onChange={setPicked} maxSlots={5} />
        </div>
      )}

      {/* Who's running this interview? Information routing only — the
          assignment shows on both sides and in the calendar exports. */}
      <fieldset className="mt-5">
        <legend className="flex items-center gap-1.5">
          <UserRound className="h-3.5 w-3.5 text-slate" />
          <MonoLabel>Who&apos;s running this interview?</MonoLabel>
        </legend>
        {fulfilling ? (
          // Locked: I'm fulfilling a scheduling request, so I'm the interviewer.
          <p className="mt-2 text-caption text-slate">
            You — {pendingRequest?.requester_name || "a teammate"} assigned this interview to you.
          </p>
        ) : (
        <div role="radiogroup" aria-label="Interviewer" className="mt-2 flex flex-wrap gap-1.5">
          {([
            ["me", "Me"],
            ["team", "Someone on my team"],
            ["other", "Someone else"],
          ] as Array<[InterviewerMode, string]>).map(([m, label]) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={mode === m}
              onClick={() => { setMode(m); setErr(null); }}
              className={[
                "rounded-full border px-3 py-1.5 text-caption font-medium transition-colors duration-200",
                mode === m
                  ? "border-cohere-ink bg-ink text-white"
                  : "border-hairline bg-white text-cohere-ink hover:border-slate",
              ].join(" ")}
            >
              {label}
            </button>
          ))}
        </div>
        )}

        {mode === "me" && (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field2 label="Your name (shown to the applicant, optional)">
              <input value={interviewerName} onChange={(e) => setInterviewerName(e.target.value)} placeholder="e.g. Jane Smith" className="input-cohere text-caption" />
            </Field2>
          </div>
        )}

        {mode === "team" && !fulfilling && (
          <>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field2 label="Teammate">
                <select
                  value={teamContactId}
                  onChange={(e) => setTeamContactId(e.target.value)}
                  className="input-cohere text-caption"
                >
                  <option value="">Pick a teammate…</option>
                  {teammates.map((t) => (
                    <option key={t.contact_id} value={t.contact_id}>
                      {teammateLabel(t)}{t.title ? ` · ${t.title}` : ""}
                    </option>
                  ))}
                </select>
                {team !== null && teammates.length === 0 && (
                  <p className="mt-1 text-micro text-slate-muted">
                    No other members on your team yet.{" "}
                    <a href="/employer/team" className="underline underline-offset-2 hover:text-cohere-ink">Invite them</a>{" "}
                    or use &ldquo;Someone else&rdquo; to enter them by name.
                  </p>
                )}
              </Field2>
              {!delegate && (
                <Field2 label="Their name (shown to the applicant)">
                  <input value={interviewerName} onChange={(e) => setInterviewerName(e.target.value)} placeholder="e.g. Marcus Lee" className="input-cohere text-caption" />
                </Field2>
              )}
            </div>

            {/* Who picks the times — paint the grid myself, or hand it to them */}
            {teammates.length > 0 && (
              pendingRequest ? (
                <p className="mt-3 text-micro text-slate-muted">
                  Already waiting on {pendingRequest.assignee_name || "a teammate"} to propose times —
                  cancel that request first to hand the time-picking to someone else.
                </p>
              ) : (
                <div className="mt-3">
                  <div role="radiogroup" aria-label="Who picks the times" className="flex flex-wrap gap-1.5">
                    {([
                      [false, "I'll pick the times"],
                      [true, chosenTeammate ? `Let ${teammateLabel(chosenTeammate).split(" ")[0] || "them"} pick the times` : "Let them pick the times"],
                    ] as Array<[boolean, string]>).map(([val, label]) => (
                      <button
                        key={String(val)}
                        type="button"
                        role="radio"
                        aria-checked={delegate === val}
                        onClick={() => { setDelegate(val); setErr(null); }}
                        className={[
                          "rounded-full border px-3 py-1.5 text-caption font-medium transition-colors duration-200",
                          delegate === val
                            ? "border-cohere-ink bg-ink text-white"
                            : "border-hairline bg-white text-cohere-ink hover:border-slate",
                        ].join(" ")}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {delegate && (
                    <div className="mt-3 space-y-3">
                      <p className="text-caption text-slate">
                        {chosenTeammate ? teammateLabel(chosenTeammate) : "They"} will be notified
                        in-app and by email with a link to this application, pick the times on their
                        own calendar, and you&apos;ll hear when they send them.
                      </p>
                      <Field2 label="Note for them (optional)">
                        <textarea
                          value={delegationNote}
                          onChange={(e) => setDelegationNote(e.target.value)}
                          rows={2}
                          placeholder="e.g. Aim for next week — mornings are best for the shop floor."
                          className="input-cohere text-caption resize-y"
                        />
                      </Field2>
                    </div>
                  )}
                </div>
              )
            )}
          </>
        )}

        {mode === "other" && (
          <>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <Field2 label="Name">
                <input value={interviewerName} onChange={(e) => setInterviewerName(e.target.value)} placeholder="e.g. Marcus Lee" className="input-cohere text-caption" />
              </Field2>
              <Field2 label="Email (optional)">
                <input type="email" value={interviewerEmail} onChange={(e) => setInterviewerEmail(e.target.value)} placeholder="marcus@company.com" className="input-cohere text-caption" />
              </Field2>
              <Field2 label="Job title (optional)">
                <input value={interviewerTitle} onChange={(e) => setInterviewerTitle(e.target.value)} placeholder="e.g. Production Supervisor" className="input-cohere text-caption" />
              </Field2>
            </div>
            <p className="mt-2 text-micro text-slate-muted">
              Want them to pick the times themselves? They need an account —{" "}
              <a href="/employer/team" className="underline underline-offset-2 hover:text-cohere-ink">
                invite them to your team
              </a>{" "}
              first.
            </p>
          </>
        )}
      </fieldset>

      {!delegating && (
        <>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <Field2 label="Location (optional)"><input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Southwire, Carrollton, GA" className="input-cohere text-caption" /></Field2>
            <Field2 label="Meeting URL (optional)"><input value={meetingUrl} onChange={(e) => setMeetingUrl(e.target.value)} placeholder="https://" className="input-cohere text-caption" /></Field2>
          </div>
          <div className="mt-3">
            <Field2 label="Note (optional)">
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="What to prepare, who they'll meet, etc." className="input-cohere text-caption resize-y" />
            </Field2>
          </div>
        </>
      )}

      <div className="mt-4 flex items-center justify-end">
        <button
          onClick={submit}
          disabled={busy || (delegating ? !teamContactId : picked.length === 0)}
          className="btn-primary inline-flex items-center gap-1.5 disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          {delegating
            ? chosenTeammate
              ? `Ask ${teammateLabel(chosenTeammate)} to pick times`
              : "Pick a teammate first"
            : picked.length === 0
              ? "Pick times to send"
              : `Send ${picked.length} time${picked.length === 1 ? "" : "s"} to applicant`}
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

// ---------------------------------------------------------------------------
// Where scheduling stands — mirrors what the applicant sees
// ---------------------------------------------------------------------------

/** "Marcus Lee (Production Supervisor)" — or null when unassigned. */
function runByLine(slot: InterviewSlot): string | null {
  const name = (slot.interviewer_name ?? "").trim();
  if (!name) return null;
  const title = (slot.interviewer_title ?? "").trim();
  return title ? `${name} (${title})` : name;
}

/** Employer-side calendar event: the candidate is the subject. */
function employerInterviewEvent(slot: InterviewSlot, app: Application): CalendarEventInput {
  const who = runByLine(slot);
  const detailBits = [
    `Interview with ${app.applicant_name || "the applicant"} for ${app.job_title}.`,
    who ? `Run by ${who}.` : null,
    slot.meeting_url ? `Join: ${slot.meeting_url}` : null,
    slot.notes || null,
  ].filter(Boolean) as string[];
  return {
    slotId: slot.id,
    title: `Interview: ${app.applicant_name || "Applicant"} (${app.job_title})`,
    description: detailBits.join("\n"),
    location: slot.location,
    meetingUrl: slot.meeting_url,
    startAt: slot.start_at,
    endAt: slot.end_at,
  };
}

function InterviewStatusSection({
  slots, proposing, app, token, readOnly, onChanged, onCancelOpenChange,
}: {
  slots: InterviewSlot[];
  proposing: boolean;
  app: Application;
  token: string;
  readOnly: boolean;
  onChanged: () => void;
  onCancelOpenChange: (open: boolean) => void;
}) {
  const accepted = slots.find((s) => s.status === "accepted");
  const proposed = slots.filter((s) => s.status === "proposed");
  const declined = slots.filter((s) => s.status === "declined");
  const superseded = slots.filter((s) => s.status === "cancelled");

  if (accepted) {
    return (
      <section className="rounded-[10px] border border-hairline bg-white p-6">
        <h2 className="text-[1.0625rem] font-medium text-cohere-green">
          Interview confirmed
          {runByLine(accepted) && (
            <span className="ml-2 text-caption font-normal text-slate">· run by {runByLine(accepted)}</span>
          )}
        </h2>
        <SlotLine slot={accepted} emphasized />
        <p className="mt-2 text-caption text-slate-muted">The applicant sees this same time on their application page.</p>
        <AddToCalendarButtons
          event={employerInterviewEvent(accepted, app)}
          className="mt-4 border-t border-hairline pt-3"
        />
        {!readOnly && (
          <CancelInterviewControl
            token={token}
            slotId={accepted.id}
            onDone={onChanged}
            onOpenChange={onCancelOpenChange}
          />
        )}
      </section>
    );
  }

  // While the propose panel is open the pending list is redundant noise.
  if (proposing) return null;

  if (proposed.length > 0) {
    return (
      <section className="rounded-[10px] border border-hairline bg-white p-6">
        <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Waiting on the applicant</h2>
        <p className="mt-1 text-caption text-slate">
          You offered {proposed.length} time{proposed.length === 1 ? "" : "s"}. They pick one, and it locks in for both of you.
          {superseded.length > 0 && <> ({superseded.length} earlier time{superseded.length === 1 ? " was" : "s were"} replaced.)</>}
        </p>
        {runByLine(proposed[0]) && (
          <p className="mt-1 inline-flex items-center gap-1.5 text-caption text-cohere-ink">
            <UserRound className="h-3.5 w-3.5 text-slate" />
            Run by <span className="font-medium">{runByLine(proposed[0])}</span>
          </p>
        )}
        <ul className="mt-3 space-y-1">
          {proposed.map((s) => <li key={s.id}><SlotLine slot={s} /></li>)}
        </ul>
        <p className="mt-3 text-micro text-slate-muted">Times shown in {browserTimeZoneLabel()}.</p>
      </section>
    );
  }

  // A booked time that was cancelled (by you, or released by the applicant's
  // withdrawal) — distinct from "the applicant declined the proposals".
  const cancelledBooked = superseded.filter((s) => s.was_accepted);
  if (cancelledBooked.length > 0) {
    return (
      <section className="rounded-[10px] border border-hairline bg-white p-6">
        <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Interview cancelled</h2>
        <p className="mt-1 text-caption text-slate">
          The booked time was cancelled and the applicant notified. Propose a new set whenever you&apos;re ready.
        </p>
      </section>
    );
  }

  if (declined.length > 0) {
    return (
      <section className="rounded-[10px] border border-hairline bg-white p-6">
        <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Times declined</h2>
        <p className="mt-1 text-caption text-slate">
          None of the {declined.length} proposed time{declined.length === 1 ? "" : "s"} worked for the applicant.
          Propose a new set whenever you&apos;re ready.
        </p>
      </section>
    );
  }

  return null;
}

/**
 * Quiet "Cancel interview" on the confirmed card. Inline confirm with an
 * optional reason that is shared with the applicant; the server returns the
 * application to its previous stage and notifies the applicant.
 */
function CancelInterviewControl({
  token, slotId, onDone, onOpenChange,
}: {
  token: string;
  slotId: string;
  onDone: () => void;
  onOpenChange: (open: boolean) => void;
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  function toggle(next: boolean) {
    setOpen(next);
    onOpenChange(next);
    if (!next) setReason("");
  }

  async function confirm() {
    setBusy(true);
    try {
      await cancelInterviewSlot(token, slotId, reason.trim() || undefined);
      toast.success("Interview cancelled. The applicant has been notified.");
      toggle(false);
      onDone();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Could not cancel the interview");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div className="mt-3 border-t border-hairline pt-3">
        <button
          type="button"
          onClick={() => toggle(true)}
          className="text-caption text-slate underline underline-offset-2 transition-colors hover:text-cohere-ink"
        >
          Cancel interview
        </button>
      </div>
    );
  }

  return (
    <div
      role="alertdialog"
      aria-label="Cancel interview"
      className="mt-4 rounded-[8px] border border-hairline bg-stone/30 p-4"
    >
      <p className="text-body font-medium text-cohere-ink">Cancel this interview?</p>
      <p className="mt-1 text-caption text-slate">
        The applicant will be notified and their application returns to its previous stage. You can propose new times later.
      </p>
      <label className="mt-3 block">
        <MonoLabel className="mb-1 block">Reason (optional, shared with the applicant)</MonoLabel>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          maxLength={500}
          placeholder="e.g. The interviewer is out that week. We will send new times."
          className="input-cohere text-caption resize-y"
        />
      </label>
      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => toggle(false)}
          disabled={busy}
          className="text-caption text-slate transition-colors hover:text-cohere-ink"
        >
          Keep it
        </button>
        <button
          type="button"
          onClick={confirm}
          disabled={busy}
          className="btn-pill-outline inline-flex items-center gap-1.5 border-studio-maroon text-studio-maroon"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
          Cancel interview
        </button>
      </div>
    </div>
  );
}

function SlotLine({ slot, emphasized = false }: { slot: InterviewSlot; emphasized?: boolean }) {
  const start = new Date(slot.start_at);
  const end = new Date(slot.end_at);
  return (
    <div className={emphasized ? "mt-2" : ""}>
      <div className={`${emphasized ? "text-body font-medium" : "text-caption"} text-cohere-ink tabular-nums`}>
        {start.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}
        {", "}
        {start.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })} – {end.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
      </div>
      {emphasized && (
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-caption text-slate">
          {slot.location && <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />{slot.location}</span>}
          {slot.meeting_url && <a href={slot.meeting_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-cohere-blue underline"><Video className="h-3.5 w-3.5" />Meeting link</a>}
        </div>
      )}
      {emphasized && slot.notes && <p className="mt-1 text-caption text-slate">{slot.notes}</p>}
    </div>
  );
}

