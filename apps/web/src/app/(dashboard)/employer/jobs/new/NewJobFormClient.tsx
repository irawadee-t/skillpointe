"use client";

/**
 * Client-side new-job form.
 *
 * Uses inline validation (min title length, pay range) via JobFormFields
 * and shows a toast on success before redirecting.
 */
import { useRouter } from "next/navigation";
import { useState } from "react";

import { JobFormFields } from "./JobFormFields";
import { ScreeningQuestionsFields } from "@/components/employer/ScreeningEditor";
import { useToast, Confetti } from "@/components/ui";
import { fireOnce } from "@/lib/milestones";
import { API_BASE } from "@/lib/api/client";
import { ScreeningQuestion, replaceEmployerScreening } from "@/lib/api/transactions";

export function NewJobFormClient({ token }: { token: string }) {
  const router = useRouter();
  const toast = useToast();
  const [valid, setValid] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [celebrate, setCelebrate] = useState(false);
  // Screening questions are edited inline and queued client-side — they save
  // right after the job exists (the API needs a job id).
  const [questions, setQuestions] = useState<ScreeningQuestion[]>([]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!valid || submitting) return;
    const formData = new FormData(e.currentTarget);
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        title_raw: formData.get("title_raw") as string,
        city: (formData.get("city") as string) || undefined,
        state: (formData.get("state") as string) || undefined,
        work_setting: (formData.get("work_setting") as string) || undefined,
        travel_requirement: (formData.get("travel_requirement") as string) || undefined,
        pay_min: formData.get("pay_min") ? Number(formData.get("pay_min")) : undefined,
        pay_max: formData.get("pay_max") ? Number(formData.get("pay_max")) : undefined,
        pay_type: (formData.get("pay_type") as string) || undefined,
        description_raw: (formData.get("description_raw") as string) || undefined,
        requirements_raw: (formData.get("requirements_raw") as string) || undefined,
        experience_level: (formData.get("experience_level") as string) || undefined,
        accepts_internal_applications: formData.get("accepts_internal_applications") === "true",
        required_profile_fields: formData.getAll("required_profile_fields").map(String),
      };
      const res = await fetch(`${API_BASE}/employer/me/jobs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const created = (await res.json().catch(() => null)) as { job_id?: string } | null;

      // Save the queued screening questions now that the job exists.
      const cleaned = questions
        .filter((q) => q.prompt.trim())
        .map((q, i) => ({ ...q, position: i }));
      if (created?.job_id && cleaned.length > 0) {
        try {
          await replaceEmployerScreening(token, created.job_id, cleaned);
        } catch {
          // The job itself is live — don't fail the flow over the questions.
          toast.error("Job posted, but the screening questions didn't save. Add them on the edit page.");
        }
      }

      // Milestone: first job posted — Confetti + special toast, then still
      // route so the employer lands on their jobs list. Confetti fires while
      // the redirect happens, which is fine because the canvas is fixed-position.
      if (fireOnce("first_job_posted")) {
        setCelebrate(true);
        toast.success("🎉 Your first job is live to matched candidates.");
      } else {
        toast.success("Job posted. Visible to matched candidates in a few minutes");
      }
      router.push("/employer/jobs");
      router.refresh();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not post job";
      setError(msg);
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-md border border-border-light bg-white p-8 space-y-6"
    >
      <Confetti active={celebrate} />
      <JobFormFields onValidChange={setValid} />

      {/* Screening questions — edited inline at create time; queued
          client-side and saved as soon as the job exists. */}
      <div className="border-t border-hairline pt-6">
        <h3 className="text-[1.0625rem] font-medium text-cohere-ink">
          Screening questions <span className="font-normal text-slate-muted">(optional)</span>
        </h3>
        <p className="mt-1 text-caption text-slate">
          Up to 5 extra questions beyond the profile. Applicants answer them inside the apply
          form. Answers that don&apos;t match your required answer flag the application so you
          can filter fast.
        </p>
        <ScreeningQuestionsFields questions={questions} onChange={setQuestions} />
      </div>

      {error && (
        <p className="text-body text-error-red" role="alert">
          {error}
        </p>
      )}
      <div className="flex items-center gap-4 pt-2">
        <button
          type="submit"
          disabled={!valid || submitting}
          className="btn-primary disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {submitting ? "Posting…" : "Post job"}
        </button>
        <a href="/employer" className="btn-secondary">
          Cancel
        </a>
      </div>
    </form>
  );
}
