"use client";

import { useEffect, useState } from "react";
import { Loader2, Send, ShieldAlert, Check, ArrowRight } from "lucide-react";

import {
  ScreeningAnswer, ScreeningQuestion,
  applyToJob, getScreeningForJob,
} from "@/lib/api/transactions";
import { MonoLabel, useToast } from "@/components/ui";

/**
 * Two-step apply flow:
 *   1. answer screening questions (if any) + optional cover note
 *   2. confirm + submit → shows the resulting Applied state inline
 *
 * Rendered as a full-width panel inside the match detail page (not a modal),
 * so it flows continuously with the rest of the match content and reads well
 * on mobile. Once submitted, the panel collapses to a confirmation card.
 */
export function ApplyFlow({
  token, jobId, matchId, jobTitle, onSubmitted,
}: {
  token: string;
  jobId: string;
  matchId?: string;
  jobTitle?: string;
  onSubmitted?: (applicationId: string) => void;
}) {
  const toast = useToast();
  const [phase, setPhase] = useState<"intro" | "screening" | "submitting" | "done">("intro");
  const [questions, setQuestions] = useState<ScreeningQuestion[] | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [coverNote, setCoverNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [applicationId, setApplicationId] = useState<string | null>(null);
  const [knockoutFailed, setKnockoutFailed] = useState(false);

  useEffect(() => {
    getScreeningForJob(token, jobId).then(setQuestions).catch(() => setQuestions([]));
  }, [token, jobId]);

  async function submit() {
    setError(null); setPhase("submitting");
    try {
      const answerList: ScreeningAnswer[] = Object.entries(answers).map(([question_id, answer]) => ({ question_id, answer }));
      const app = await applyToJob(token, jobId, {
        answers: answerList,
        cover_note: coverNote.trim() || undefined,
      });
      setApplicationId(app.id);
      setKnockoutFailed(app.knockout_failed);
      setPhase("done");
      toast.success("Sent. The employer will see it in their inbox.");
      onSubmitted?.(app.id);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not submit";
      setError(msg);
      toast.error(msg);
      setPhase(questions && questions.length > 0 ? "screening" : "intro");
    }
  }

  if (phase === "done") {
    return (
      <section className="rounded-xl border border-cohere-green/30 bg-wash-green p-6">
        <div className="flex items-center gap-2">
          <Check className="h-5 w-5 text-cohere-green" strokeWidth={2} />
          <h3 className="font-display text-feature text-cohere-ink">
            {knockoutFailed ? "Sent — with one flag" : "Sent"}
          </h3>
        </div>
        <p className="mt-2 text-body text-cohere-ink">
          {knockoutFailed
            ? "One of your answers didn't match a hard requirement. The employer can still see it and decide — we'll let you know if they respond."
            : "The employer will review it and can propose interview times. We'll let you know when they respond."}
        </p>
        {applicationId && (
          <a
            href={`/applicant/applications/${applicationId}`}
            className="btn-primary mt-4 inline-flex items-center gap-1.5"
          >
            See it in your applications <ArrowRight className="h-4 w-4" />
          </a>
        )}
      </section>
    );
  }

  if (phase === "intro" || !questions) {
    const hasQuestions = questions && questions.length > 0;
    return (
      <section className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <MonoLabel className="text-studio-maroon">Send your application</MonoLabel>
            <h3 className="mt-2 font-display text-feature text-cohere-ink">{jobTitle ? `Apply for ${jobTitle}` : "Apply on SKILLED"}</h3>
            <p className="mt-2 max-w-prose text-body text-slate">
              {hasQuestions
                ? "A couple of quick questions from the employer, then your profile goes straight to them."
                : "Your profile and verified credentials go straight to the employer. Nothing else to fill in."}
            </p>
          </div>
          <button
            onClick={() => hasQuestions ? setPhase("screening") : submit()}
            disabled={questions === null || phase === "submitting"}
            className="btn-primary-green shrink-0 inline-flex items-center gap-1.5"
          >
            {questions === null || phase === "submitting"
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : hasQuestions
                ? <>Continue <ArrowRight className="h-4 w-4" /></>
                : <>Send application <Send className="h-4 w-4" /></>}
          </button>
        </div>

        {error && <p className="mt-3 text-caption text-studio-maroon">{error}</p>}

        {!hasQuestions && (
          <div className="mt-5 space-y-3">
            <label className="block">
              <MonoLabel className="mb-1.5 block">Add a note (optional)</MonoLabel>
              <textarea
                value={coverNote}
                onChange={(e) => setCoverNote(e.target.value)}
                rows={3}
                placeholder="Say something short about why you're a fit."
                className="input-cohere min-h-[80px] resize-y"
                maxLength={2000}
              />
            </label>
            <div className="flex items-center justify-end">
              <button onClick={submit} disabled={phase === "submitting"} className="btn-primary-green inline-flex items-center gap-1.5">
                {phase === "submitting" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Send application
              </button>
            </div>
          </div>
        )}
      </section>
    );
  }

  // Screening phase
  const remaining = questions.filter((q) => q.is_knockout && !answers[q.id!]).length;
  const canSubmit = remaining === 0;
  return (
    <section className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <MonoLabel className="text-studio-maroon">Step 2 of 2</MonoLabel>
          <h3 className="mt-2 font-display text-feature text-cohere-ink">A few questions from the employer</h3>
          <p className="mt-1 text-caption text-slate">Some employers require these before they'll look at an application.</p>
        </div>
        <button onClick={() => setPhase("intro")} className="text-caption text-slate hover:text-cohere-ink">← Back</button>
      </div>

      {error && <p className="mt-3 text-caption text-studio-maroon">{error}</p>}

      <div className="mt-5 space-y-4">
        {questions.map((q, i) => (
          <QuestionRow key={q.id ?? i} q={q} value={answers[q.id!] ?? ""}
            onChange={(v) => setAnswers((prev) => ({ ...prev, [q.id!]: v }))} />
        ))}
      </div>

      <div className="mt-5 border-t border-hairline pt-5">
        <MonoLabel className="mb-1.5 block">Add a note (optional)</MonoLabel>
        <textarea
          value={coverNote}
          onChange={(e) => setCoverNote(e.target.value)}
          rows={2}
          placeholder="Optional note to the employer."
          className="input-cohere min-h-[64px] resize-y"
          maxLength={2000}
        />
      </div>

      <div className="mt-5 flex items-center justify-between">
        {remaining > 0 ? (
          <p className="inline-flex items-center gap-1.5 text-caption text-studio-maroon">
            <ShieldAlert className="h-3.5 w-3.5" /> {remaining} required question{remaining === 1 ? "" : "s"} left
          </p>
        ) : <span />}
        <button onClick={submit} disabled={!canSubmit || phase === "submitting"} className="btn-primary-green inline-flex items-center gap-1.5">
          {phase === "submitting" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          Send application
        </button>
      </div>
    </section>
  );
}

function QuestionRow({ q, value, onChange }: { q: ScreeningQuestion; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <div className="flex items-baseline gap-1.5">
        <p className="font-medium text-cohere-ink">{q.prompt}</p>
        {q.is_knockout && <span className="text-micro text-studio-maroon">required</span>}
      </div>
      {q.kind === "yes_no" && (
        <div className="mt-2 inline-flex overflow-hidden rounded-full border border-hairline">
          {["Yes", "No"].map((opt) => (
            <button key={opt} type="button" onClick={() => onChange(opt)}
              className={`px-4 py-1.5 text-caption font-medium transition-colors ${value === opt ? "bg-studio-dark-cork text-white" : "text-slate hover:text-cohere-ink"}`}>
              {opt}
            </button>
          ))}
        </div>
      )}
      {q.kind === "multiple_choice" && (
        <div className="mt-2 flex flex-wrap gap-2">
          {q.options.map((opt) => (
            <button key={opt} type="button" onClick={() => onChange(opt)}
              className={`rounded-full border px-3 py-1 text-caption transition-colors ${value === opt ? "border-cohere-ink bg-studio-dark-cork text-white" : "border-hairline text-slate hover:border-cohere-ink hover:text-cohere-ink"}`}>
              {opt}
            </button>
          ))}
        </div>
      )}
      {q.kind === "short_text" && (
        <input value={value} onChange={(e) => onChange(e.target.value)} className="input-cohere mt-2" maxLength={280} />
      )}
    </div>
  );
}
