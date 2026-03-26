"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { createClient } from "@/lib/supabase/client";
import {
  US_STATES,
  CAREER_PATHS,
  PROGRAM_FIELDS,
  ENROLLMENT_STATUSES,
  DEGREE_TYPES,
  TRAVEL_OPTIONS,
  RELOCATION_OPTIONS,
  WAGE_RANGES,
  AGE_RANGES,
  GENDER_OPTIONS,
} from "@/lib/constants";

type FormState = Record<string, unknown>;

export default function EditProfilePage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [form, setForm] = useState<FormState>({});

  useEffect(() => {
    async function load() {
      const supabase = createClient();
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { router.push("/login"); return; }

      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/applicant/me/profile`,
        { headers: { Authorization: `Bearer ${session.access_token}` } }
      );
      if (!resp.ok) { setLoading(false); return; }

      const data = await resp.json();
      setForm({
        first_name: data.first_name ?? "",
        last_name: data.last_name ?? "",
        program_name_raw: data.program_name_raw ?? "",
        city: data.city ?? "",
        state: data.state ?? "",
        willing_to_relocate: data.willing_to_relocate ?? false,
        willing_to_travel: data.willing_to_travel ?? false,
        expected_completion_date: data.expected_completion_date ?? "",
        available_from_date: data.available_from_date ?? "",
        enrollment_status: data.enrollment_status ?? "",
        degree_type: data.degree_type ?? "",
        school_name: data.school_name ?? "",
        school_city: data.school_city ?? "",
        school_state: data.school_state ?? "",
        career_path: data.career_path ?? "",
        program_field: data.program_field ?? "",
        specific_career: data.specific_career ?? "",
        program_start_date: data.program_start_date ?? "",
        gpa: data.gpa ?? "",
        travel_preference: data.travel_preference ?? "within_state",
        relocation_preference: data.relocation_preference ?? "stay_current",
        relocation_states: data.relocation_states ?? [],
        age_range: data.age_range ?? "",
        gender: data.gender ?? "",
        military_status: data.military_status ?? false,
        military_dependent: data.military_dependent ?? false,
        current_wages: data.current_wages ?? "",
        has_internship: data.has_internship ?? false,
        activities: data.activities ?? "",
      });
      setLoading(false);
    }
    load();
  }, [router]);

  function set(field: string, value: unknown) {
    setForm((f) => ({ ...f, [field]: value }));
    setSaved(false);
  }

  const filteredPrograms = useMemo(() => {
    if (!form.career_path) return PROGRAM_FIELDS;
    return PROGRAM_FIELDS.filter((p) => p.careerPath === form.career_path);
  }, [form.career_path]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);

    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { router.push("/login"); return; }

    const payload: Record<string, unknown> = { ...form, onboarding_complete: true };

    // Clean empty strings → omit from PATCH
    for (const key of Object.keys(payload)) {
      if (payload[key] === "" || payload[key] === null) delete payload[key];
    }
    // Convert GPA to number
    if (typeof payload.gpa === "string" && payload.gpa) {
      payload.gpa = parseFloat(payload.gpa as string) || undefined;
    }
    // Derive legacy booleans from new enums for backward compat
    if (payload.travel_preference) {
      payload.willing_to_travel = payload.travel_preference !== "no_travel";
    }
    if (payload.relocation_preference) {
      payload.willing_to_relocate = payload.relocation_preference !== "stay_current";
    }

    const resp = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/applicant/me/profile`,
      {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }
    );

    setSaving(false);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      setError(err.detail ?? "Save failed. Please try again.");
      return;
    }

    setSaved(true);
    router.refresh();
  }

  if (loading) {
    return (
      <main className="flex items-center justify-center p-20">
        <p className="text-zinc-400 text-sm">Loading profile...</p>
      </main>
    );
  }

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-2xl mx-auto">
        <Link
          href="/applicant"
          className="text-sm text-zinc-400 hover:text-white mb-6 inline-flex items-center gap-1 transition-colors"
        >
          &larr; Back to dashboard
        </Link>

        <h1 className="text-2xl font-semibold tracking-tight text-white mb-6">Edit profile</h1>

        <form onSubmit={handleSubmit} className="space-y-6">

          {/* ---- Basic Info ---- */}
          <Section title="Basic info">
            <Row>
              <Field label="First name">
                <Input value={form.first_name as string} onChange={(v) => set("first_name", v)} placeholder="Jane" />
              </Field>
              <Field label="Last name">
                <Input value={form.last_name as string} onChange={(v) => set("last_name", v)} placeholder="Smith" />
              </Field>
            </Row>
            <Row>
              <Field label="Age range">
                <Select value={form.age_range as string} onChange={(v) => set("age_range", v)} options={AGE_RANGES.map((a) => ({ value: a, label: a }))} />
              </Field>
              <Field label="Gender">
                <Select value={form.gender as string} onChange={(v) => set("gender", v)} options={GENDER_OPTIONS.map((g) => ({ value: g, label: g }))} />
              </Field>
            </Row>
            <Row>
              <Field label="Military">
                <Checkbox checked={form.military_status as boolean} onChange={(v) => set("military_status", v)} label="I have served or am serving in the military" />
              </Field>
              <Field label="">
                <Checkbox checked={form.military_dependent as boolean} onChange={(v) => set("military_dependent", v)} label="Military spouse/dependent" />
              </Field>
            </Row>
          </Section>

          {/* ---- Education ---- */}
          <Section title="Education">
            <Row>
              <Field label="Current enrollment">
                <Select value={form.enrollment_status as string} onChange={(v) => set("enrollment_status", v)} options={ENROLLMENT_STATUSES.map((e) => ({ value: e.value, label: e.label }))} />
              </Field>
              <Field label="Degree type">
                <Select value={form.degree_type as string} onChange={(v) => set("degree_type", v)} options={DEGREE_TYPES.map((d) => ({ value: d.value, label: d.label }))} />
              </Field>
            </Row>
            <Field label="School name">
              <Input value={form.school_name as string} onChange={(v) => set("school_name", v)} placeholder="e.g. Penn College of Technology" />
            </Field>
            <Row>
              <Field label="School city">
                <Input value={form.school_city as string} onChange={(v) => set("school_city", v)} placeholder="Williamsport" />
              </Field>
              <Field label="School state">
                <Select value={form.school_state as string} onChange={(v) => set("school_state", v)} options={US_STATES.map((s) => ({ value: s, label: s }))} />
              </Field>
            </Row>
            <Field label="GPA (if applicable)">
              <Input value={String(form.gpa ?? "")} onChange={(v) => set("gpa", v)} placeholder="3.5" type="number" step="0.01" min="0" max="4" />
            </Field>
          </Section>

          {/* ---- Program & Career ---- */}
          <Section title="Program & career path">
            <Field label="Career path">
              <Select value={form.career_path as string} onChange={(v) => { set("career_path", v); set("program_field", ""); }} options={CAREER_PATHS.map((c) => ({ value: c.value, label: c.label }))} />
            </Field>
            <Field label="Program / field of study">
              <Select value={form.program_field as string} onChange={(v) => set("program_field", v)} options={filteredPrograms.map((p) => ({ value: p.value, label: p.label }))} />
            </Field>
            <Field label="Specific career or program name">
              <Input value={form.specific_career as string} onChange={(v) => set("specific_career", v)} placeholder="e.g. A.A.S. Building Construction Technologies" />
              <p className="text-xs text-zinc-500 mt-1">Free text — describe exactly what you study or want to do</p>
            </Field>
            <Field label="Program name (as you know it)">
              <Input value={form.program_name_raw as string} onChange={(v) => set("program_name_raw", v)} placeholder="e.g. Electrician Apprentice" />
              <p className="text-xs text-zinc-500 mt-1">Auto-matched to a job family when you save</p>
            </Field>
          </Section>

          {/* ---- Dates & Availability ---- */}
          <Section title="Program dates & availability">
            <Row>
              <Field label="Program start date">
                <Input type="date" value={form.program_start_date as string} onChange={(v) => set("program_start_date", v)} />
              </Field>
              <Field label="Expected completion date">
                <Input type="date" value={form.expected_completion_date as string} onChange={(v) => set("expected_completion_date", v)} />
              </Field>
            </Row>
            <Field label="Available to start work">
              <Input type="date" value={form.available_from_date as string} onChange={(v) => set("available_from_date", v)} />
              <p className="text-xs text-zinc-500 mt-1">When can you start a new job?</p>
            </Field>
            <Field label="Current wages">
              <Select value={form.current_wages as string} onChange={(v) => set("current_wages", v)} options={WAGE_RANGES.map((w) => ({ value: w.value, label: w.label }))} />
            </Field>
          </Section>

          {/* ---- Location ---- */}
          <Section title="Location">
            <Row>
              <Field label="City">
                <Input value={form.city as string} onChange={(v) => set("city", v)} placeholder="San Jose" />
              </Field>
              <Field label="State">
                <Select value={form.state as string} onChange={(v) => set("state", v)} options={US_STATES.map((s) => ({ value: s, label: s }))} />
              </Field>
            </Row>
          </Section>

          {/* ---- Travel & Relocation ---- */}
          <Section title="Travel & relocation preferences">
            <Field label="Willingness to travel for work">
              <div className="space-y-2">
                {TRAVEL_OPTIONS.map((opt) => (
                  <label key={opt.value} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${form.travel_preference === opt.value ? "border-cyan-500 bg-cyan-500/10" : "border-zinc-700 hover:border-zinc-500"}`}>
                    <input
                      type="radio"
                      name="travel_preference"
                      value={opt.value}
                      checked={form.travel_preference === opt.value}
                      onChange={() => set("travel_preference", opt.value)}
                      className="mt-0.5 accent-cyan-500"
                    />
                    <div>
                      <span className="text-sm font-medium text-white">{opt.label}</span>
                      <p className="text-xs text-zinc-400">{opt.desc}</p>
                    </div>
                  </label>
                ))}
              </div>
            </Field>

            <Field label="Willingness to relocate">
              <div className="space-y-2">
                {RELOCATION_OPTIONS.map((opt) => (
                  <label key={opt.value} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${form.relocation_preference === opt.value ? "border-cyan-500 bg-cyan-500/10" : "border-zinc-700 hover:border-zinc-500"}`}>
                    <input
                      type="radio"
                      name="relocation_preference"
                      value={opt.value}
                      checked={form.relocation_preference === opt.value}
                      onChange={() => set("relocation_preference", opt.value)}
                      className="mt-0.5 accent-cyan-500"
                    />
                    <div>
                      <span className="text-sm font-medium text-white">{opt.label}</span>
                      <p className="text-xs text-zinc-400">{opt.desc}</p>
                    </div>
                  </label>
                ))}
              </div>
            </Field>

            {form.relocation_preference === "specific_states" && (
              <Field label="Which states would you relocate to?">
                <div className="grid grid-cols-5 sm:grid-cols-8 gap-1.5 max-h-48 overflow-y-auto border border-zinc-700 rounded-lg p-3">
                  {US_STATES.map((s) => {
                    const selected = (form.relocation_states as string[] || []).includes(s);
                    return (
                      <button
                        key={s}
                        type="button"
                        onClick={() => {
                          const current = (form.relocation_states as string[]) || [];
                          set("relocation_states", selected ? current.filter((x) => x !== s) : [...current, s]);
                        }}
                        className={`text-xs font-mono py-1.5 rounded transition-colors ${selected ? "bg-cyan-500 text-black font-medium" : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"}`}
                      >
                        {s}
                      </button>
                    );
                  })}
                </div>
                {(form.relocation_states as string[])?.length > 0 && (
                  <p className="text-xs text-zinc-500 mt-1">
                    Selected: {(form.relocation_states as string[]).join(", ")}
                  </p>
                )}
              </Field>
            )}
          </Section>

          {/* ---- Experience ---- */}
          <Section title="Experience">
            <Checkbox
              checked={form.has_internship as boolean}
              onChange={(v) => set("has_internship", v)}
              label="I have completed an internship or work experience"
            />
            <Field label="Activities & extracurriculars">
              <textarea
                value={form.activities as string}
                onChange={(e) => set("activities", e.target.value)}
                rows={3}
                className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500 resize-none"
                placeholder="Clubs, sports, volunteer work, SkillsUSA, FFA, etc."
              />
            </Field>
          </Section>

          {/* ---- Submit ---- */}
          {error && (
            <p className="text-sm text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded-lg p-3">{error}</p>
          )}
          {saved && (
            <p className="text-sm text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-3">
              Profile saved. Your program has been automatically matched to a job family.
            </p>
          )}

          <div className="flex gap-3">
            <Link href="/applicant" className="flex-1 border border-zinc-700 text-zinc-300 py-2.5 rounded-full text-sm font-medium hover:border-zinc-500 hover:text-white transition-colors text-center">
              Cancel
            </Link>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 bg-cyan-500 text-black py-2.5 rounded-full text-sm font-medium hover:bg-cyan-400 disabled:opacity-50 transition-colors"
            >
              {saving ? "Saving..." : "Save changes"}
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}

/* ---- Reusable sub-components ---- */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-5">
      <h2 className="font-semibold text-white">{title}</h2>
      {children}
    </div>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-4">{children}</div>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      {label && <label className="block text-sm font-medium text-zinc-300 mb-1">{label}</label>}
      {children}
    </div>
  );
}

function Input({
  value, onChange, placeholder, type = "text", step, min, max,
}: {
  value: string; onChange: (v: string) => void; placeholder?: string;
  type?: string; step?: string; min?: string; max?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      step={step}
      min={min}
      max={max}
      className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
    />
  );
}

function Select({
  value, onChange, options,
}: {
  value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
    >
      <option value="">Select...</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

function Checkbox({
  checked, onChange, label,
}: {
  checked: boolean; onChange: (v: boolean) => void; label: string;
}) {
  return (
    <label className="flex items-center gap-3 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-4 h-4 rounded border-zinc-600 accent-cyan-500"
      />
      <span className="text-sm text-zinc-300">{label}</span>
    </label>
  );
}
