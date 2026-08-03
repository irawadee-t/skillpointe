"use client";

/**
 * ApplySheet — the one-click in-platform application flow.
 *
 * Opens as a fast confirmation sheet (centered dialog on desktop, bottom sheet
 * on mobile). One review step when the profile already covers everything the
 * employer requires — "Applying with your SKILLED profile" plus a single
 * commit button. Missing required fields are completed INLINE (saved back to
 * the profile, labeled as such) — the user is never bounced to the profile
 * page. Employer extra questions appear as a short second step in the same
 * sheet.
 *
 * The review step IS the consent moment: it lists exactly what will be shared,
 * and the server freezes that snapshot on the application row.
 *
 * Edge cases handled here: already-applied on open, withdrawn → one re-apply,
 * job gone inactive (honest error), internal apply disabled, double-submit
 * (server-idempotent + button pending state), required-question validation
 * (client + 422 server parity), long answers (limits + counters), keyboard
 * focus trap, Escape with confirm-if-dirty, reduced motion, view-as read-only.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AnimatePresence, motion, MotionConfig,
} from "motion/react";
import {
  ArrowRight, Check, Loader2, Send, ShieldAlert, UploadCloud, X,
} from "lucide-react";

import {
  Application, ApplyContext, PROFILE_GROUP_LABELS, ProfileGroupKey,
  ProfileInlineUpdates, ScreeningQuestion,
  applyToJob, getApplyContext,
} from "@/lib/api/transactions";
import { parseResume } from "@/lib/api/robustness";
import { ApiError } from "@/lib/api/client";
import { formatDate, formatDateShort } from "@/lib/format";
import { consumeApplyReturn, setApplyReturn } from "@/lib/applyReturn";
import { useToast } from "@/components/ui";
import { useViewAs, VIEW_AS_READONLY_TOOLTIP } from "@/hooks/useViewAs";

const easeSheet: [number, number, number, number] = [0.16, 1, 0.3, 1];

function errorDetail(e: unknown, fallback: string): string {
  if (e instanceof ApiError) {
    try {
      const parsed = JSON.parse(e.body);
      if (typeof parsed?.detail === "string") return parsed.detail;
    } catch { /* raw body below */ }
    if (e.body) return e.body.slice(0, 300);
  }
  return e instanceof Error ? e.message : fallback;
}

export function ApplySheet({
  token, jobId, jobTitle, open, onClose, onApplied,
}: {
  token: string;
  jobId: string;
  jobTitle?: string;
  open: boolean;
  onClose: () => void;
  /** Fires on successful submit so the caller can flip to "Applied · Just now". */
  onApplied?: (app: Application) => void;
}) {
  const toast = useToast();
  const { isViewAs } = useViewAs();

  const [ctx, setCtx] = useState<ApplyContext | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [step, setStep] = useState<"review" | "questions" | "done">("review");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [inline, setInline] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [resumeUploaded, setResumeUploaded] = useState<string | null>(null);
  const [resumeUploading, setResumeUploading] = useState(false);
  const [doneApp, setDoneApp] = useState<Application | null>(null);

  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Return-trip honor: if the user was sent to /applicant/credentials from
  // THIS job's sheet and came back, reopen the sheet automatically. Covers
  // parents that keep the sheet mounted with open=false (e.g. ApplyFlow);
  // list pages that mount the sheet lazily consume the pending return
  // themselves via consumeApplyReturn().
  const [selfOpen, setSelfOpen] = useState(false);
  useEffect(() => {
    if (consumeApplyReturn(jobId)) setSelfOpen(true);
  }, [jobId]);
  const isOpen = open || selfOpen;

  // Focus restore: remember the element that opened the sheet, refocus on close.
  useEffect(() => {
    if (isOpen && document.activeElement instanceof HTMLElement) {
      triggerRef.current = document.activeElement;
    }
  }, [isOpen]);

  const handleClose = useCallback(() => {
    setSelfOpen(false);
    onClose();
    const trigger = triggerRef.current;
    if (trigger && document.contains(trigger)) trigger.focus();
  }, [onClose]);

  // Load context each time the sheet opens; reset transient state.
  useEffect(() => {
    if (!isOpen) return;
    setCtx(null); setLoadError(null); setStep("review");
    setAnswers({}); setInline({}); setNote("");
    setServerError(null); setConfirmClose(false);
    setResumeUploaded(null); setDoneApp(null);
    getApplyContext(token, jobId)
      .then(setCtx)
      .catch((e: unknown) => setLoadError(errorDetail(e, "Could not load this job right now.")));
  }, [isOpen, token, jobId]);

  const dirty = useMemo(
    () =>
      Object.values(answers).some((v) => v.trim()) ||
      Object.values(inline).some((v) => v.trim()) ||
      note.trim().length > 0,
    [answers, inline, note],
  );

  const requestClose = useCallback(() => {
    if (submitting) return;
    if (dirty && step !== "done" && !doneApp) {
      setConfirmClose(true);
      return;
    }
    handleClose();
  }, [submitting, dirty, step, doneApp, handleClose]);

  // Focus trap + Escape. The sheet is the only interactive surface while open.
  useEffect(() => {
    if (!isOpen) return;
    const panel = panelRef.current;
    // Move focus into the sheet after the entrance settles.
    const t = setTimeout(() => {
      const first = panel?.querySelector<HTMLElement>(
        "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])",
      );
      first?.focus();
    }, 50);

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        requestClose();
        return;
      }
      if (e.key !== "Tab" || !panel) return;
      const focusables = Array.from(
        panel.querySelectorAll<HTMLElement>(
          "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
        ),
      ).filter((el) => el.offsetParent !== null);
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => { clearTimeout(t); document.removeEventListener("keydown", onKeyDown); };
  }, [isOpen, requestClose]);

  // ----- Derived flow state --------------------------------------------------

  const questions: ScreeningQuestion[] = ctx?.questions ?? [];
  const hasQuestions = questions.length > 0;

  const missing = useMemo<ProfileGroupKey[]>(() => {
    if (!ctx) return [];
    return ctx.missing_required.filter((g) => !(g === "resume" && resumeUploaded));
  }, [ctx, resumeUploaded]);

  /** Groups the inline form can actually complete with typed input. */
  const typedMissing = missing.filter((g) => g !== "resume" && g !== "credentials");
  const resumeMissing = missing.includes("resume");
  const credentialsMissing = missing.includes("credentials");

  const inlineComplete = typedMissing.every((g) => {
    if (g === "contact") return (inline["phone"] ?? "").trim().length >= 7;
    if (g === "location") return (inline["city"] ?? "").trim() && (inline["state"] ?? "").trim();
    if (g === "program") return (inline["program_name_raw"] ?? "").trim();
    if (g === "availability") return (inline["available_from_date"] ?? "").trim();
    return true;
  });

  const reviewReady = inlineComplete && !resumeMissing && !credentialsMissing;

  const requiredUnanswered = questions.filter(
    (q) => q.is_knockout && !(answers[q.id!] ?? "").trim(),
  ).length;

  function buildProfileUpdates(): ProfileInlineUpdates | undefined {
    const upd: ProfileInlineUpdates = {};
    if ((inline["phone"] ?? "").trim()) upd.phone = inline["phone"].trim();
    if ((inline["city"] ?? "").trim()) upd.city = inline["city"].trim();
    if ((inline["state"] ?? "").trim()) upd.state = inline["state"].trim();
    if ((inline["program_name_raw"] ?? "").trim()) upd.program_name_raw = inline["program_name_raw"].trim();
    if ((inline["available_from_date"] ?? "").trim()) upd.available_from_date = inline["available_from_date"].trim();
    return Object.keys(upd).length > 0 ? upd : undefined;
  }

  async function submit() {
    if (submitting || isViewAs) return;
    setSubmitting(true);
    setServerError(null);
    try {
      const app = await applyToJob(token, jobId, {
        answers: Object.entries(answers)
          .filter(([, v]) => v.trim())
          .map(([question_id, answer]) => ({ question_id, answer })),
        cover_note: note.trim() || undefined,
        profile_updates: buildProfileUpdates(),
      });
      setDoneApp(app);
      setStep("done");
      toast.success("Application sent");
      onApplied?.(app);
    } catch (e: unknown) {
      const msg = errorDetail(e, "Could not submit. Try again.");
      if (e instanceof ApiError && e.status === 409 && /already/i.test(msg)) {
        // Double-submit or applied in another tab — treat as an honest,
        // friendly terminal state rather than an error wall.
        setServerError(null);
        setCtx((c) => c ? { ...c, already_applied: c.already_applied ?? {
          id: "", status: "submitted", submitted_at: new Date().toISOString(), can_reapply: false,
        } } : c);
        setStep("review");
        toast.info?.("You've already applied to this job.");
        setServerError("You've already applied to this job.");
      } else {
        setServerError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  }

  function primaryAction() {
    if (!reviewReady) return;
    if (hasQuestions && step === "review") {
      setStep("questions");
      return;
    }
    void submit();
  }

  async function onResumeFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setResumeUploading(true);
    setServerError(null);
    try {
      await parseResume(token, f);
      setResumeUploaded(f.name);
    } catch (err: unknown) {
      setServerError(errorDetail(err, "Could not read that file."));
    } finally {
      setResumeUploading(false);
    }
  }

  // ----- Render --------------------------------------------------------------

  const titleId = "apply-sheet-title";

  return (
    <MotionConfig reducedMotion="user">
      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="apply-overlay"
            className="fixed inset-0 z-50 flex items-end justify-center sm:items-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            aria-hidden={false}
          >
            {/* Backdrop */}
            <div
              className="absolute inset-0 bg-ink/30"
              onClick={requestClose}
              aria-hidden="true"
            />

            {/* Panel */}
            <motion.div
              ref={panelRef}
              role="dialog"
              aria-modal="true"
              aria-labelledby={titleId}
              className="relative w-full max-h-[88vh] overflow-y-auto rounded-t-[14px] border border-hairline bg-white shadow-float sm:max-w-lg sm:rounded-[14px]"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.3, ease: easeSheet }}
            >
              {/* Header */}
              <div className="flex items-start justify-between gap-3 px-5 pt-5 sm:px-6 sm:pt-6">
                <div className="min-w-0">
                  <p className="text-[11px] font-medium text-studio-maroon">
                    {step === "done" ? "Application sent" : "Apply on SKILLED Nation"}
                  </p>
                  <h2 id={titleId} className="mt-1 text-[1.0625rem] font-medium leading-snug text-cohere-ink">
                    {jobTitle ?? ctx?.job_title ?? "This job"}
                    {ctx?.employer_name ? <span className="text-slate"> · {ctx.employer_name}</span> : null}
                  </h2>
                </div>
                <button
                  onClick={requestClose}
                  aria-label="Close"
                  className="shrink-0 rounded-full border border-hairline p-1.5 text-slate transition-colors duration-200 hover:text-cohere-ink active:scale-[0.97]"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="px-5 pb-5 pt-4 sm:px-6 sm:pb-6">
                {/* Loading */}
                {!ctx && !loadError && (
                  <div className="flex items-center gap-2 py-8 text-body text-slate">
                    <Loader2 className="h-4 w-4 animate-spin" /> Getting your application ready…
                  </div>
                )}

                {loadError && (
                  <p className="py-6 text-body text-studio-maroon">{loadError}</p>
                )}

                {/* Terminal: already applied (and no re-apply available) */}
                {ctx && step !== "done" && ctx.already_applied && !ctx.already_applied.can_reapply && (
                  <AlreadyApplied info={ctx.already_applied} onClose={handleClose} />
                )}

                {/* Terminal: job inactive */}
                {ctx && !ctx.job_active && !ctx.already_applied && (
                  <div className="py-4">
                    <p className="text-body text-cohere-ink">This job is no longer accepting applications.</p>
                    <button onClick={handleClose} className="btn-ghost mt-4">Close</button>
                  </div>
                )}

                {/* Terminal: internal apply not available */}
                {ctx && ctx.job_active && !ctx.internal_apply_enabled && !ctx.already_applied && (
                  <div className="py-4">
                    <p className="text-body text-cohere-ink">
                      This job takes applications on the employer&apos;s site.
                    </p>
                    {ctx.external_url && (
                      <a href={ctx.external_url} target="_blank" rel="noopener noreferrer" className="btn-ghost mt-4 inline-flex items-center gap-1.5">
                        Apply on employer site ↗
                      </a>
                    )}
                  </div>
                )}

                {/* Step: review — the consent moment */}
                {ctx && ctx.job_active && ctx.internal_apply_enabled &&
                  (!ctx.already_applied || ctx.already_applied.can_reapply) &&
                  step === "review" && (
                  <ReviewStep
                    ctx={ctx}
                    jobId={jobId}
                    jobTitle={jobTitle}
                    inline={inline}
                    setInline={setInline}
                    typedMissing={typedMissing}
                    resumeMissing={resumeMissing}
                    credentialsMissing={credentialsMissing}
                    resumeUploaded={resumeUploaded}
                    resumeUploading={resumeUploading}
                    onResumeFile={onResumeFile}
                  />
                )}

                {/* Step: questions */}
                {ctx && step === "questions" && (
                  <QuestionsStep
                    questions={questions}
                    answers={answers}
                    setAnswers={setAnswers}
                    note={note}
                    setNote={setNote}
                    onBack={() => setStep("review")}
                  />
                )}

                {/* Step: done */}
                {step === "done" && doneApp && (
                  <div className="py-2">
                    <div className="flex items-center gap-2">
                      <Check className="h-5 w-5 text-cohere-green" strokeWidth={2} />
                      <p className="text-body text-cohere-ink">
                        {doneApp.knockout_failed
                          ? "Sent. One answer didn't match a requirement, so the employer will see a flag and decide."
                          : "The employer will review it and can propose interview times."}
                      </p>
                    </div>
                    <div className="mt-5 flex items-center gap-3">
                      <a href={`/applicant/applications/${doneApp.id}`} className="btn-primary inline-flex items-center gap-1.5">
                        See it in your applications <ArrowRight className="h-4 w-4" />
                      </a>
                      <button onClick={handleClose} className="btn-ghost">Done</button>
                    </div>
                  </div>
                )}

                {serverError && step !== "done" && (
                  <p className="mt-3 text-caption text-studio-maroon" role="alert">{serverError}</p>
                )}

                {/* Footer: commit actions */}
                {ctx && ctx.job_active && ctx.internal_apply_enabled &&
                  (!ctx.already_applied || ctx.already_applied.can_reapply) &&
                  step !== "done" && (
                  <div className="mt-5 flex items-center justify-between gap-3 border-t border-hairline pt-4">
                    {step === "questions" && requiredUnanswered > 0 ? (
                      <p className="inline-flex items-center gap-1.5 text-caption text-studio-maroon">
                        <ShieldAlert className="h-3.5 w-3.5" />
                        {requiredUnanswered} required question{requiredUnanswered === 1 ? "" : "s"} left
                      </p>
                    ) : (
                      <p className="text-caption text-slate-muted">
                        {ctx.already_applied?.can_reapply
                          ? "Re-applying after you withdrew. This is your one re-apply."
                          : hasQuestions && step === "review"
                            ? "One more short step after this."
                            : "Sent straight to the employer."}
                      </p>
                    )}
                    <button
                      onClick={step === "questions" ? () => void submit() : primaryAction}
                      disabled={
                        submitting || isViewAs ||
                        (step === "review" && !reviewReady) ||
                        (step === "questions" && requiredUnanswered > 0)
                      }
                      title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
                      className="btn-commit inline-flex shrink-0 items-center gap-1.5 transition-transform duration-100 active:scale-[0.97] disabled:opacity-50"
                    >
                      {submitting ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : step === "review" && hasQuestions ? (
                        <>Continue <ArrowRight className="h-4 w-4" /></>
                      ) : (
                        <>Send application <Send className="h-4 w-4" /></>
                      )}
                    </button>
                  </div>
                )}

                {/* Confirm-if-dirty on Escape / close */}
                <AnimatePresence>
                  {confirmClose && (
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 8 }}
                      transition={{ duration: 0.2, ease: easeSheet }}
                      className="mt-4 flex items-center justify-between gap-3 rounded-[10px] border border-hairline bg-white p-3"
                    >
                      <p className="text-caption text-cohere-ink">Discard this application?</p>
                      <div className="flex items-center gap-2">
                        <button onClick={() => setConfirmClose(false)} className="btn-ghost !py-1 text-caption">Keep editing</button>
                        <button onClick={handleClose} className="rounded-full border border-hairline px-3 py-1 text-caption text-studio-maroon transition-colors duration-200 hover:border-studio-maroon active:scale-[0.97]">
                          Discard
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </MotionConfig>
  );
}

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

function AlreadyApplied({ info, onClose }: {
  info: NonNullable<ApplyContext["already_applied"]>;
  onClose: () => void;
}) {
  const when = formatDateShort(info.submitted_at);
  return (
    <div className="py-4">
      <div className="flex items-center gap-2">
        <Check className="h-5 w-5 text-cohere-green" strokeWidth={2} />
        <p className="text-body text-cohere-ink">
          {info.status === "withdrawn"
            ? "You applied, withdrew, and used your one re-apply for this job."
            : `You've already applied (${when}).`}
        </p>
      </div>
      <div className="mt-4 flex items-center gap-3">
        {info.id && (
          <a href={`/applicant/applications/${info.id}`} className="btn-primary inline-flex items-center gap-1.5">
            View your application <ArrowRight className="h-4 w-4" />
          </a>
        )}
        <button onClick={onClose} className="btn-ghost">Close</button>
      </div>
    </div>
  );
}

function ReviewStep({
  ctx, jobId, jobTitle, inline, setInline, typedMissing, resumeMissing, credentialsMissing,
  resumeUploaded, resumeUploading, onResumeFile,
}: {
  ctx: ApplyContext;
  jobId: string;
  jobTitle?: string;
  inline: Record<string, string>;
  setInline: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  typedMissing: ProfileGroupKey[];
  resumeMissing: boolean;
  credentialsMissing: boolean;
  resumeUploaded: string | null;
  resumeUploading: boolean;
  onResumeFile: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  const p = ctx.profile;
  const shared = ctx.required_fields.length > 0 ? ctx.required_fields : (["contact", "location", "program"] as ProfileGroupKey[]);

  function sharedValue(group: ProfileGroupKey): string | null {
    switch (group) {
      case "contact": {
        const parts = [p.phone, p.email].filter(Boolean);
        return parts.length ? parts.join(" · ") : null;
      }
      case "location":
        return p.city && p.state ? `${p.city}, ${p.state}` : null;
      case "program":
        return p.program;
      case "availability":
        return p.available_from_date
          ? `Available from ${formatDate(p.available_from_date)}`
          : p.expected_completion_date
            ? `Program ends ${formatDate(p.expected_completion_date)}`
            : null;
      case "credentials":
        return p.credentials.length ? p.credentials.slice(0, 4).join(", ") : null;
      case "resume":
        return resumeUploaded ?? p.resume_filename;
    }
  }

  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setInline((prev) => ({ ...prev, [key]: e.target.value }));

  return (
    <div>
      <p className="text-body text-slate">
        Applying with your SKILLED profile. Here&apos;s exactly what {ctx.employer_name ?? "the employer"} will see:
      </p>

      {/* What will be shared — grouped, compact hairline rows */}
      <div className="mt-4 rounded-[10px] border border-hairline bg-white">
        {shared.map((group, i) => {
          const value = sharedValue(group);
          const isMissing = ctx.missing_required.includes(group) && !(group === "resume" && resumeUploaded);
          return (
            <div key={group} className={`px-4 py-2.5 ${i > 0 ? "border-t border-hairline" : ""}`}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-caption text-slate">{PROFILE_GROUP_LABELS[group]}</span>
                {!isMissing && value && (
                  <span className="min-w-0 truncate text-caption text-cohere-ink">{value}</span>
                )}
                {!isMissing && !value && (
                  <span className="text-caption text-slate-muted">Not provided</span>
                )}
                {isMissing && group !== "resume" && group !== "credentials" && (
                  <span className="text-[11px] font-medium text-studio-maroon">needed</span>
                )}
              </div>

              {/* Inline-complete: typed groups */}
              {isMissing && typedMissing.includes(group) && (
                <div className="mt-2">
                  {group === "contact" && (
                    <input
                      type="tel" inputMode="tel" value={inline["phone"] ?? ""} onChange={set("phone")}
                      placeholder="Phone number" maxLength={40}
                      className="input-cohere" aria-label="Phone number"
                    />
                  )}
                  {group === "location" && (
                    <div className="grid grid-cols-[1fr_5rem] gap-2">
                      <input value={inline["city"] ?? ""} onChange={set("city")} placeholder="City" maxLength={120} className="input-cohere" aria-label="City" />
                      <input value={inline["state"] ?? ""} onChange={set("state")} placeholder="State" maxLength={2} className="input-cohere uppercase" aria-label="State" />
                    </div>
                  )}
                  {group === "program" && (
                    <input value={inline["program_name_raw"] ?? ""} onChange={set("program_name_raw")} placeholder="e.g. Welding technology" maxLength={200} className="input-cohere" aria-label="Program or trade" />
                  )}
                  {group === "availability" && (
                    <input type="date" value={inline["available_from_date"] ?? ""} onChange={set("available_from_date")} className="input-cohere" aria-label="Available from" />
                  )}
                  <p className="mt-1 text-[11px] text-slate-muted">Saved to your profile too.</p>
                </div>
              )}

              {/* Inline-complete: resume upload */}
              {group === "resume" && resumeMissing && (
                <div className="mt-2">
                  <label className="btn-ghost inline-flex cursor-pointer items-center gap-1.5 !py-1.5 text-caption">
                    {resumeUploading
                      ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      : <UploadCloud className="h-3.5 w-3.5" />}
                    {resumeUploading ? "Uploading…" : "Upload a resume"}
                    <input type="file" accept=".pdf,.docx,.txt,application/pdf" className="hidden" onChange={onResumeFile} disabled={resumeUploading} />
                  </label>
                  <p className="mt-1 text-[11px] text-slate-muted">This employer asks for a resume. It saves to your profile too.</p>
                </div>
              )}

              {/* Credentials can't be typed inline — honest block. The link
                  goes to the credentials page with a return marker; when the
                  user comes back, the sheet reopens on this job automatically. */}
              {group === "credentials" && credentialsMissing && (
                <p className="mt-2 text-caption text-studio-maroon">
                  This employer asks for at least one credential on your profile.{" "}
                  <a
                    href={`/applicant/credentials?return=${encodeURIComponent(jobId)}`}
                    onClick={() =>
                      setApplyReturn({
                        jobId,
                        href: window.location.pathname + window.location.search,
                        title: jobTitle ?? ctx.job_title,
                      })
                    }
                    className="underline"
                  >
                    Add one on your credentials page
                  </a>
                  . We&apos;ll bring you back and reopen this application.
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function QuestionsStep({
  questions, answers, setAnswers, note, setNote, onBack,
}: {
  questions: ScreeningQuestion[];
  answers: Record<string, string>;
  setAnswers: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  note: string;
  setNote: (v: string) => void;
  onBack: () => void;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-body text-slate">A few questions from the employer.</p>
        <button onClick={onBack} className="text-caption text-slate transition-colors duration-200 hover:text-cohere-ink">← Back</button>
      </div>

      <div className="mt-4 space-y-4">
        {questions.map((q, i) => (
          <SheetQuestion
            key={q.id ?? i}
            q={q}
            value={answers[q.id!] ?? ""}
            onChange={(v) => setAnswers((prev) => ({ ...prev, [q.id!]: v }))}
          />
        ))}
      </div>

      <label className="mt-5 block border-t border-hairline pt-4">
        <span className="text-caption text-slate">Add a note (optional)</span>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          maxLength={2000}
          placeholder="Anything short you want the employer to know."
          className="input-cohere mt-1.5 min-h-[56px] resize-y"
        />
        {note.length > 1800 && (
          <span className="mt-1 block text-right text-[11px] tabular-nums text-slate-muted">{note.length}/2000</span>
        )}
      </label>
    </div>
  );
}

function SheetQuestion({ q, value, onChange }: {
  q: ScreeningQuestion; value: string; onChange: (v: string) => void;
}) {
  return (
    <div>
      <div className="flex items-baseline gap-1.5">
        <p className="text-body font-medium text-cohere-ink">{q.prompt}</p>
        <span className="text-[11px] text-slate-muted">{q.is_knockout ? "required" : "optional"}</span>
      </div>
      {q.kind === "yes_no" && (
        <div className="mt-2 inline-flex overflow-hidden rounded-full border border-hairline">
          {["Yes", "No"].map((opt) => (
            <button
              key={opt} type="button" onClick={() => onChange(opt)}
              className={`px-4 py-1.5 text-caption font-medium transition-colors duration-200 active:scale-[0.97] ${value === opt ? "bg-ink text-white" : "text-slate hover:text-cohere-ink"}`}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
      {q.kind === "multiple_choice" && (
        <div className="mt-2 flex flex-wrap gap-2">
          {q.options.map((opt) => (
            <button
              key={opt} type="button" onClick={() => onChange(opt)}
              className={`rounded-full border px-3 py-1 text-caption transition-colors duration-200 active:scale-[0.97] ${value === opt ? "border-cohere-ink bg-ink text-white" : "border-hairline text-slate hover:border-cohere-ink hover:text-cohere-ink"}`}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
      {q.kind === "short_text" && (
        <div className="mt-2">
          <input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="input-cohere"
            maxLength={280}
            aria-label={q.prompt}
          />
          {value.length > 220 && (
            <span className="mt-1 block text-right text-[11px] tabular-nums text-slate-muted">{value.length}/280</span>
          )}
        </div>
      )}
    </div>
  );
}
