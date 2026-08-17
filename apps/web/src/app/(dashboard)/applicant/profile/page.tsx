"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { createClient } from "@/lib/supabase/client";
import { SectorFieldSelect, sectorFieldFromCodes } from "@/components/taxonomy/SectorFieldSelect";
import { PreferencesPanel } from "@/components/applicant/PreferencesPanel";
import { ResumeUploader } from "@/components/applicant/ResumeUploader";
import { useAutosave } from "@/lib/useAutosave";
import { SaveIndicator } from "@/components/ui/SaveIndicator";
import { useViewAs, VIEW_AS_READONLY_TOOLTIP } from "@/hooks/useViewAs";
import {
  US_STATES,
  ENROLLMENT_STATUSES,
  DEGREE_TYPES,
  TRAVEL_OPTIONS,
  RELOCATION_OPTIONS,
  COMMUTE_RADIUS_PRESETS,
  WAGE_RANGES,
  AGE_RANGES,
  GENDER_OPTIONS,
} from "@/lib/constants";

type FormState = Record<string, unknown>;

/**
 * Build the PATCH payload from form state.
 *
 * Every managed field is sent — an explicitly-emptied field goes as `null`
 * (rather than being omitted) so clearing e.g. city actually persists. We only
 * ever send keys the form itself manages; `extra` merges in fields the form
 * doesn't own (e.g. onboarding_complete on an explicit save).
 */
function buildProfilePayload(
  form: FormState,
  extra?: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(form)) {
    out[k] = v === "" || v === undefined ? null : v;
  }
  // GPA: numeric or null (empty clears it).
  if (typeof form.gpa === "string") {
    out.gpa = form.gpa.trim() === "" ? null : parseFloat(form.gpa) || null;
  }
  // Commute radius: integer miles or null (empty clears it).
  if ("commute_radius_miles" in form) {
    const raw = form.commute_radius_miles;
    const n = typeof raw === "string" ? parseInt(raw, 10) : (raw as number | null);
    out.commute_radius_miles = n && n > 0 ? Math.min(n, 500) : null;
  }
  // Derive legacy booleans from the new enum fields for backward compat.
  if (form.travel_preference) out.willing_to_travel = form.travel_preference !== "no_travel";
  if (form.relocation_preference) out.willing_to_relocate = form.relocation_preference !== "stay_current";
  return { ...out, ...extra };
}

export default function EditProfilePage() {
  const router = useRouter();
  const { isViewAs } = useViewAs();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [form, setForm] = useState<FormState>({});

  // Autosave: after the first load, silently PATCH ~800ms after every edit.
  // Skips onboarding_complete so we don't accidentally finalize onboarding here.
  const autosave = useAutosave(loading || isViewAs ? null : form, 800, async (payload) => {
    if (!payload) return;
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return;
    const body = buildProfilePayload(payload as FormState);
    const resp = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/applicant/me/profile`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${session.access_token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    // Surface a real failure to the autosave hook (→ "error" state) instead of
    // silently showing "Saved" on a 4xx/5xx.
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail ?? `Autosave failed (${resp.status})`);
    }
  });

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
        phone: data.phone ?? "",
        program_name_raw: data.program_name_raw ?? "",
        city: data.city ?? "",
        state: data.state ?? "",
        commute_radius_miles: data.commute_radius_miles ?? "",
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
        ...((): Record<string, unknown> => {
          const seeded = sectorFieldFromCodes(data.sector_code, data.canonical_job_family_code);
          return { sector_code: seeded.sectorCode ?? "", field_code: seeded.fieldCode ?? "" };
        })(),
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


  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);

    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { router.push("/login"); return; }

    // Send every managed field (emptied → null) so clearing a field persists.
    const payload = buildProfilePayload(form, { onboarding_complete: true });

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
    // Skeleton loader (item 19) — same shell as the loaded form so the layout
    // doesn't jump when data arrives. Uses hairline-toned pulse blocks.
    return (
      <main className="py-8">
        <div className="mx-auto w-full max-w-3xl px-5">
          <div className="mb-6 h-4 w-32 animate-pulse rounded bg-hairline" />
          <div className="mb-6 flex items-center justify-between">
            <div className="h-8 w-40 animate-pulse rounded bg-hairline" />
            <div className="h-4 w-24 animate-pulse rounded bg-hairline" />
          </div>
          <div className="mb-6 h-24 animate-pulse rounded-xl bg-hairline/60" />
          <div className="space-y-6">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="space-y-3 rounded-md border border-border-light bg-white p-6">
                <div className="h-5 w-40 animate-pulse rounded bg-hairline" />
                <div className="grid grid-cols-2 gap-4">
                  <div className="h-9 animate-pulse rounded bg-hairline/70" />
                  <div className="h-9 animate-pulse rounded bg-hairline/70" />
                </div>
                <div className="h-9 animate-pulse rounded bg-hairline/70" />
              </div>
            ))}
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="py-8">
      <div className="mx-auto w-full max-w-3xl px-5">
        <Link
          href="/applicant"
          className="text-body text-slate hover:text-cohere-ink mb-6 inline-flex items-center gap-1 transition-colors"
        >
          &larr; Back to dashboard
        </Link>

        {/* Sticky header — keeps SaveIndicator visible as the applicant scrolls
            through the long autosaved form so they never wonder if changes stuck. */}
        <div className="sticky top-0 z-20 -mx-5 mb-6 flex items-center justify-between gap-3 border-b border-hairline bg-canvas/95 px-5 py-3 backdrop-blur supports-[backdrop-filter]:bg-canvas/80">
          <h1 className="font-display text-card sm:text-heading text-cohere-ink">Edit profile</h1>
          <SaveIndicator status={autosave.status} lastSavedAt={autosave.lastSavedAt} />
        </div>

        {/* Shortcut: upload a resume to auto-populate the fields below. Rendered
            above the manual form so it's the first thing a returning worker sees. */}
        <ResumeAutoFillShortcut onFilled={(fields) => setForm((prev) => ({ ...prev, ...fields }))} />

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
            <Field label="Phone">
              <PhoneInput value={(form.phone as string) ?? ""} onChange={(v) => set("phone", v)} />
              <p className="text-micro text-slate-muted mt-1">Used for text notifications when you turn them on.</p>
            </Field>
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
            <div className="md:col-span-2">
              <SectorFieldSelect
                sectorCode={form.sector_code as string}
                fieldCode={form.field_code as string}
                onChange={(v) => {
                  set("sector_code", v.sectorCode);
                  set("field_code", v.fieldCode);
                  set("career_path", v.sectorName);
                  set("program_field", v.fieldName);
                }}
              />
            </div>
            <Field label="Specific career or program name">
              <Input value={form.specific_career as string} onChange={(v) => set("specific_career", v)} placeholder="e.g. A.A.S. Building Construction Technologies" />
              <p className="text-micro text-slate-muted mt-1">Free text. Describe exactly what you study or want to do</p>
            </Field>
            <Field label="Program name (as you know it)">
              <Input value={form.program_name_raw as string} onChange={(v) => set("program_name_raw", v)} placeholder="e.g. Electrician Apprentice" />
              <p className="text-micro text-slate-muted mt-1">Auto-matched to a job family when you save</p>
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
              <p className="text-micro text-slate-muted mt-1">When can you start a new job?</p>
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
            <Field label="How far will you travel for work?">
              <div className="flex flex-wrap items-center gap-2">
                {COMMUTE_RADIUS_PRESETS.map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => set("commute_radius_miles", r)}
                    aria-pressed={Number(form.commute_radius_miles) === r}
                    className={`rounded-full border px-4 py-1.5 text-caption transition-colors ${Number(form.commute_radius_miles) === r ? "border-cohere-ink bg-ink font-medium text-white" : "border-hairline bg-white text-slate hover:border-cohere-ink"}`}
                  >
                    {r} mi
                  </button>
                ))}
                <div className="flex items-center gap-1.5">
                  <input
                    type="number"
                    min={1}
                    max={500}
                    value={(form.commute_radius_miles as number | string) ?? ""}
                    onChange={(e) => set("commute_radius_miles", e.target.value)}
                    className="input-cohere w-24"
                    placeholder="50"
                    aria-label="Commute radius in miles"
                  />
                  <span className="text-caption text-slate-muted">miles</span>
                </div>
              </div>
              <p className="text-micro text-slate-muted mt-1.5">
                Jobs within this distance of {(form.city as string) || "your home city"}
                {form.state ? `, ${form.state}` : ""} count as in range, including jobs in
                nearby cities your radius covers. Your matches update when you change it.
              </p>
            </Field>
          </Section>

          {/* ---- Travel & Relocation ---- */}
          <Section title="Travel & relocation preferences">
            <Field label="Willing to travel for work">
              <div className="space-y-2">
                {TRAVEL_OPTIONS.map((opt) => (
                  <label key={opt.value} className={`flex items-start gap-3 p-3 rounded-sm border cursor-pointer transition-colors ${form.travel_preference === opt.value ? "border-cohere-ink bg-stone" : "border-hairline hover:border-cohere-ink"}`}>
                    <input
                      type="radio"
                      name="travel_preference"
                      value={opt.value}
                      checked={form.travel_preference === opt.value}
                      onChange={() => set("travel_preference", opt.value)}
                      className="mt-0.5 accent-cohere-ink"
                    />
                    <div>
                      <span className="text-body font-medium text-cohere-ink">{opt.label}</span>
                      <p className="text-caption text-slate">{opt.desc}</p>
                    </div>
                  </label>
                ))}
              </div>
            </Field>

            <Field label="Willing to relocate">
              <div className="space-y-2">
                {RELOCATION_OPTIONS.map((opt) => (
                  <label key={opt.value} className={`flex items-start gap-3 p-3 rounded-sm border cursor-pointer transition-colors ${form.relocation_preference === opt.value ? "border-cohere-ink bg-stone" : "border-hairline hover:border-cohere-ink"}`}>
                    <input
                      type="radio"
                      name="relocation_preference"
                      value={opt.value}
                      checked={form.relocation_preference === opt.value}
                      onChange={() => set("relocation_preference", opt.value)}
                      className="mt-0.5 accent-cohere-ink"
                    />
                    <div>
                      <span className="text-body font-medium text-cohere-ink">{opt.label}</span>
                      <p className="text-caption text-slate">{opt.desc}</p>
                    </div>
                  </label>
                ))}
              </div>
            </Field>

            {form.relocation_preference === "specific_states" && (
              <Field label="Which states would you relocate to?">
                <div className="grid grid-cols-5 sm:grid-cols-8 gap-1.5 max-h-48 overflow-y-auto border border-hairline rounded-sm p-3">
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
                        className={`text-micro py-1.5 rounded-sm transition-colors ${selected ? "bg-ink text-white font-medium" : "bg-stone text-slate hover:bg-hairline hover:text-ink"}`}
                      >
                        {s}
                      </button>
                    );
                  })}
                </div>
                {(form.relocation_states as string[])?.length > 0 && (
                  <p className="text-micro text-slate-muted mt-1">
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
                className="input-cohere resize-none"
                placeholder="Clubs, sports, volunteer work, SkillsUSA, FFA, etc."
              />
            </Field>
          </Section>

          <Section title="Notifications & language">
            <PreferencesPanelWrapper />
          </Section>

          {/* ---- Submit ---- */}
          {error && (
            <p className="text-body text-cohere-ink bg-error-red/[0.06] border border-error-red/30 rounded-md p-3">{error}</p>
          )}
          {saved && (
            <p className="text-body text-cohere-ink bg-wash-green border border-cohere-green/30 rounded-md p-3">
              Profile saved. Your program has been automatically matched to a job family.
            </p>
          )}

          <div className="flex gap-3">
            <Link href="/applicant" className="btn-pill-outline flex-1 text-center">
              Cancel
            </Link>
            <button
              type="submit"
              disabled={saving || isViewAs}
              title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
              className="btn-primary flex-1 disabled:opacity-50"
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

/**
 * Collapsible shortcut for auto-populating the profile from a resume upload.
 * Keeps the profile page clean by default — one row with an icon and CTA — then
 * expands the full ResumeUploader in place when the applicant taps "Upload."
 */
function ResumeAutoFillShortcut({ onFilled }: { onFilled: (fields: Record<string, unknown>) => void }) {
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    createClient().auth.getSession().then(({ data }) => setToken(data.session?.access_token ?? null));
  }, []);

  if (open && token) {
    return (
      <section className="mb-6">
        <ResumeUploader token={token} onApplied={(fields) => { onFilled(fields); setOpen(false); }} />
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="mt-2 text-caption text-slate hover:text-cohere-ink"
        >
          Cancel
        </button>
      </section>
    );
  }

  return (
    <section
      className="mb-6 flex flex-col gap-3 rounded-xl border border-hairline bg-white p-5 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="min-w-0">
        <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Have a resume already?</h2>
        <p className="mt-1 text-caption text-slate">Drop it here and we'll pre-fill what we can read. You review every field before anything saves.</p>
      </div>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="btn-pill-outline shrink-0"
      >
        Upload resume
      </button>
    </section>
  );
}

function PreferencesPanelWrapper() {
  const [token, setToken] = useState<string | null>(null);
  useEffect(() => {
    createClient().auth.getSession().then(({ data }) => setToken(data.session?.access_token ?? null));
  }, []);
  if (!token) return <p className="text-caption text-slate-muted">Loading…</p>;
  return <PreferencesPanel token={token} />;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-border-light rounded-md p-6 space-y-5">
      <h2 className="text-[1.0625rem] font-medium text-cohere-ink">{title}</h2>
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
      {label && <label className="block text-micro font-medium tracking-wide text-slate mb-2">{label}</label>}
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
      className="input-cohere"
    />
  );
}

/**
 * Phone input with the same inline validation the apply sheet uses (a real
 * number is at least 7 characters). Validates on blur; the hint clears as
 * soon as the value is fixed or emptied.
 */
function PhoneInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [touched, setTouched] = useState(false);
  const invalid = touched && value.trim().length > 0 && value.trim().length < 7;
  return (
    <>
      <input
        type="tel"
        inputMode="tel"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => setTouched(true)}
        placeholder="(555) 555-0100"
        maxLength={40}
        aria-invalid={invalid || undefined}
        className={`input-cohere ${invalid ? "border-studio-maroon" : ""}`}
      />
      {invalid && (
        <p className="text-micro text-studio-maroon mt-1" role="alert">
          That number looks too short. Enter at least 7 digits.
        </p>
      )}
    </>
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
      className="input-cohere"
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
        className="w-4 h-4 rounded-sm border-hairline accent-cohere-ink"
      />
      <span className="text-body text-slate">{label}</span>
    </label>
  );
}
