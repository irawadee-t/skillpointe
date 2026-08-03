"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, Loader2, Check } from "lucide-react";

import {
  ScreeningQuestion,
  getEmployerScreening, replaceEmployerScreening,
} from "@/lib/api/transactions";
import { MonoLabel } from "@/components/ui";

/**
 * Presentational editor for a list of screening questions — no fetching, no
 * saving. Used by ScreeningEditor (edit-job, saves per jobId) and by the
 * create-job form, which queues questions client-side and saves them right
 * after the job exists.
 */
export function ScreeningQuestionsFields({
  questions,
  onChange,
}: {
  questions: ScreeningQuestion[];
  onChange: (qs: ScreeningQuestion[]) => void;
}) {
  function add() {
    if (questions.length >= 5) return;
    onChange([...questions, {
      position: questions.length,
      kind: "yes_no",
      prompt: "",
      options: [],
      required_answer: "Yes",
      is_knockout: true,
    }]);
  }

  function update(i: number, patch: Partial<ScreeningQuestion>) {
    onChange(questions.map((q, ix) => ix === i ? { ...q, ...patch } : q));
  }

  function remove(i: number) {
    onChange(questions.filter((_, ix) => ix !== i));
  }

  return (
    <>
      <div className="mt-5 space-y-4">
        {questions.map((q, i) => (
          <div key={i} className="rounded-lg border border-hairline bg-stone/30 p-4">
            <div className="flex items-start justify-between gap-3">
              <MonoLabel>Question {i + 1}</MonoLabel>
              <button type="button" onClick={() => remove(i)} aria-label="Remove" className="text-slate-muted hover:text-studio-maroon">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
            <input
              value={q.prompt}
              onChange={(e) => update(i, { prompt: e.target.value })}
              placeholder="e.g. Do you have a valid CDL Class A?"
              className="input-cohere mt-2 text-caption"
              maxLength={280}
            />
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <label className="block">
                <MonoLabel className="mb-1 block">Answer type</MonoLabel>
                <select value={q.kind} onChange={(e) => update(i, { kind: e.target.value as ScreeningQuestion["kind"] })} className="input-cohere text-caption">
                  <option value="yes_no">Yes / No</option>
                  <option value="multiple_choice">Multiple choice</option>
                  <option value="short_text">Short answer</option>
                </select>
              </label>

              {q.kind === "yes_no" && (
                <label className="block">
                  <MonoLabel className="mb-1 block">Required answer</MonoLabel>
                  <select value={q.required_answer ?? "Yes"} onChange={(e) => update(i, { required_answer: e.target.value })} className="input-cohere text-caption">
                    <option value="Yes">Yes</option>
                    <option value="No">No</option>
                  </select>
                </label>
              )}

              {q.kind === "multiple_choice" && (
                <label className="block sm:col-span-2">
                  <MonoLabel className="mb-1 block">Options (comma-separated) &middot; required = first</MonoLabel>
                  <input
                    value={q.options.join(", ")}
                    onChange={(e) => {
                      const opts = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
                      update(i, { options: opts, required_answer: opts[0] ?? null });
                    }}
                    className="input-cohere text-caption"
                    placeholder="Level 1, Level 2, Level 3+"
                  />
                </label>
              )}

              {q.kind !== "multiple_choice" && (
                <label className="block sm:col-span-1">
                  <MonoLabel className="mb-1 block">Required</MonoLabel>
                  <select value={q.is_knockout ? "yes" : "no"} onChange={(e) => update(i, { is_knockout: e.target.value === "yes" })} className="input-cohere text-caption">
                    <option value="yes">Required (must answer)</option>
                    <option value="no">Optional</option>
                  </select>
                </label>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-5">
        <button
          type="button"
          onClick={add}
          disabled={questions.length >= 5}
          className="inline-flex items-center gap-1 text-caption text-cohere-blue disabled:text-slate-muted"
        >
          <Plus className="h-3.5 w-3.5" /> Add question ({questions.length}/5)
        </button>
      </div>
    </>
  );
}

/**
 * Reusable editor for a job's 0–5 screening questions.
 * Called on the "post a job" flow and on the edit-job form.
 */
export function ScreeningEditor({ token, jobId }: { token: string; jobId: string }) {
  const [questions, setQuestions] = useState<ScreeningQuestion[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getEmployerScreening(token, jobId).then((qs) => { setQuestions(qs); setLoading(false); }).catch(() => setLoading(false));
  }, [token, jobId]);

  async function save() {
    setSaving(true); setErr(null); setSaved(false);
    try {
      const cleaned = questions
        .filter((q) => q.prompt.trim())
        .map((q, i) => ({ ...q, position: i }));
      const fresh = await replaceEmployerScreening(token, jobId, cleaned);
      setQuestions(fresh);
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="flex items-center gap-2 text-caption text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading questions…</div>;
  }

  return (
    <section className="rounded-xl border border-hairline bg-white p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[1.0625rem] font-medium text-cohere-ink">Screening questions</h3>
          <p className="mt-1 text-caption text-slate">
            Up to 5 extra questions beyond the profile. Applicants answer them inside
            the apply form. Answers that don&apos;t match your required answer flag the
            application so you can filter fast.
          </p>
        </div>
        {saved && <span className="inline-flex items-center gap-1 text-caption text-cohere-green"><Check className="h-3.5 w-3.5" /> Saved</span>}
      </div>

      {err && <p className="mt-3 text-caption text-studio-maroon">{err}</p>}

      <ScreeningQuestionsFields questions={questions} onChange={setQuestions} />

      <div className="mt-4 flex justify-end">
        <button onClick={save} disabled={saving} className="btn-primary inline-flex items-center gap-1.5">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          Save screening
        </button>
      </div>
    </section>
  );
}
