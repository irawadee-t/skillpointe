"use client";

/**
 * Employer onboarding wizard — 3-step self-serve flow.
 *
 * Step 1, Company    — name, industry, city, state, website, description (≤400)
 * Step 2, Contact    — hiring lead title + confirm phone/timezone (display-only)
 * Step 3, First job  — CTA to /employer/jobs/new  OR  "Skip for now"
 *
 * On submit of Step 1+2, POST /employer/me/company/create. Step 3 has no submit —
 * the employer record already exists at that point.
 */
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight, Briefcase, CheckCircle2 } from "lucide-react";

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

// Local-storage keys for resumable onboarding. Mirrors the applicant setup flow
// (applicant.setup.step / .form): a partial exit (reload, accidental nav away)
// should resume where the employer left off rather than reset to step 1.
const ONBOARD_STEP_KEY = "employer.onboarding.step";
const ONBOARD_COMPANY_KEY = "employer.onboarding.company";
const ONBOARD_CONTACT_KEY = "employer.onboarding.contact";

function persistDraft(key: string, value: unknown) {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(key, JSON.stringify(value)); } catch { /* silent */ }
}
function clearOnboardingDraft() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(ONBOARD_STEP_KEY);
    window.localStorage.removeItem(ONBOARD_COMPANY_KEY);
    window.localStorage.removeItem(ONBOARD_CONTACT_KEY);
  } catch { /* silent */ }
}

const INDUSTRIES = [
  "Advanced Manufacturing",
  "Aerospace",
  "Automotive",
  "Construction",
  "Electrical",
  "Energy & Utilities",
  "HVAC",
  "Industrial Maintenance",
  "Logistics & Warehousing",
  "Mechanical",
  "Plumbing",
  "Skilled Trades — Other",
  "Technology",
  "Transportation",
  "Welding & Fabrication",
];

const US_STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS",
  "KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY",
  "NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV",
  "WI","WY","DC",
];

type Step = 1 | 2 | 3;

interface CompanyForm {
  name: string;
  industry: string;
  city: string;
  state: string;
  website: string;
  description: string;
}

interface ContactForm {
  full_name: string;
  contact_title: string;
  phone: string;
  timezone: string;
}

export function EmployerOnboardingWizard({
  token,
  suggestedContactName,
  contactEmail,
}: {
  token: string;
  suggestedContactName: string | null;
  contactEmail: string | null;
}) {
  const router = useRouter();
  const [step, _setStep] = useState<Step>(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [company, _setCompany] = useState<CompanyForm>({
    name: "",
    industry: "",
    city: "",
    state: "",
    website: "",
    description: "",
  });

  const [contact, _setContact] = useState<ContactForm>({
    full_name: suggestedContactName ?? "",
    contact_title: "",
    phone: "",
    timezone:
      typeof Intl !== "undefined"
        ? Intl.DateTimeFormat().resolvedOptions().timeZone || ""
        : "",
  });

  // Persist-on-change wrappers so every edit survives a reload.
  const setStep = (next: Step) => {
    _setStep(next);
    // Step 3 = company already created server-side → the draft is obsolete.
    if (next === 3) clearOnboardingDraft();
    else persistDraft(ONBOARD_STEP_KEY, next);
  };
  const setCompany = (v: CompanyForm) => { _setCompany(v); persistDraft(ONBOARD_COMPANY_KEY, v); };
  const setContact = (v: ContactForm) => { _setContact(v); persistDraft(ONBOARD_CONTACT_KEY, v); };

  // Resume: rehydrate step + drafts from localStorage on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const savedCompany = window.localStorage.getItem(ONBOARD_COMPANY_KEY);
      if (savedCompany) _setCompany((prev) => ({ ...prev, ...JSON.parse(savedCompany) }));
      const savedContact = window.localStorage.getItem(ONBOARD_CONTACT_KEY);
      if (savedContact) _setContact((prev) => ({ ...prev, ...JSON.parse(savedContact) }));
      const savedStep = window.localStorage.getItem(ONBOARD_STEP_KEY);
      if (savedStep) {
        const n = parseInt(savedStep, 10) as Step;
        // Only steps 1–2 are resumable; step 3 implies the company already exists.
        if (n === 1 || n === 2) _setStep(n);
      }
    } catch { /* silent */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const step1Valid = company.name.trim().length >= 2;
  const step2Valid = contact.full_name.trim().length >= 2;

  async function submitCreate() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/employer/me/company/create`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: company.name.trim(),
          industry: company.industry || null,
          city: company.city || null,
          state: company.state || null,
          website: company.website || null,
          description: company.description || null,
          contact_title: contact.contact_title || null,
        }),
      });
      if (res.status === 409) {
        // Already linked — jump to dashboard.
        clearOnboardingDraft();
        router.push("/employer");
        router.refresh();
        return;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Server error ${res.status}`);
      }
      setStep(3);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create company");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <p className="mono-label text-slate-muted">Employer onboarding</p>
        <h1 className="font-display text-heading text-cohere-ink leading-tight">
          Set up your company
        </h1>
        <p className="text-body text-slate">
          Three quick steps to start receiving ranked candidate matches.
        </p>
      </header>

      <StepDots current={step} />

      <div className="rounded-md border border-hairline bg-white p-6">
        {step === 1 && (
          <StepCompany
            value={company}
            onChange={setCompany}
            onNext={() => setStep(2)}
            valid={step1Valid}
          />
        )}
        {step === 2 && (
          <StepContact
            value={contact}
            onChange={setContact}
            email={contactEmail}
            onBack={() => setStep(1)}
            onNext={submitCreate}
            valid={step2Valid}
            submitting={submitting}
          />
        )}
        {step === 3 && <StepFirstJob />}

        {error && (
          <p role="alert" className="mt-4 text-body text-error-red">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StepDots({ current }: { current: Step }) {
  const items: { n: Step; label: string }[] = [
    { n: 1, label: "Company" },
    { n: 2, label: "Contact" },
    { n: 3, label: "First job" },
  ];
  return (
    <ol className="flex items-center gap-3">
      {items.map((it, i) => {
        const done = current > it.n;
        const active = current === it.n;
        return (
          <li key={it.n} className="flex items-center gap-3">
            <span
              className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-micro font-medium tabular-nums ${
                done
                  ? "bg-cohere-green text-white"
                  : active
                    ? "bg-studio-maroon text-white"
                    : "bg-stone text-slate-muted"
              }`}
            >
              {done ? "✓" : it.n}
            </span>
            <span
              className={`text-caption ${
                active
                  ? "font-medium text-cohere-ink"
                  : done
                    ? "text-slate"
                    : "text-slate-muted"
              }`}
            >
              {it.n}. {it.label}
            </span>
            {i < items.length - 1 && (
              <span aria-hidden className="h-px w-6 bg-hairline" />
            )}
          </li>
        );
      })}
    </ol>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="mono-label text-slate">{label}</span>
      {children}
      {hint && <span className="block text-caption text-slate-muted">{hint}</span>}
    </label>
  );
}

const INPUT_CLASS =
  "w-full rounded-sm border border-hairline bg-white px-3 py-2 text-body text-cohere-ink placeholder:text-slate-muted focus:border-cohere-ink focus:outline-none focus:ring-2 focus:ring-cohere-ink/10";

function StepCompany({
  value,
  onChange,
  onNext,
  valid,
}: {
  value: CompanyForm;
  onChange: (v: CompanyForm) => void;
  onNext: () => void;
  valid: boolean;
}) {
  const patch = (p: Partial<CompanyForm>) => onChange({ ...value, ...p });
  const descLen = value.description.length;
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onNext();
      }}
    >
      <div>
        <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Company profile</h2>
        <p className="mt-1 text-caption text-slate">
          Tell candidates who they&apos;d be applying to.
        </p>
      </div>

      <Field label="Company name">
        <input
          required
          type="text"
          value={value.name}
          onChange={(e) => patch({ name: e.target.value })}
          className={INPUT_CLASS}
          placeholder="e.g. Southwire Company"
        />
      </Field>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Industry">
          <select
            value={value.industry}
            onChange={(e) => patch({ industry: e.target.value })}
            className={INPUT_CLASS}
          >
            <option value="">Select…</option>
            {INDUSTRIES.map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Website" hint="Optional">
          <input
            type="url"
            value={value.website}
            onChange={(e) => patch({ website: e.target.value })}
            className={INPUT_CLASS}
            placeholder="https://…"
          />
        </Field>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_140px]">
        <Field label="City">
          <input
            type="text"
            value={value.city}
            onChange={(e) => patch({ city: e.target.value })}
            className={INPUT_CLASS}
            placeholder="e.g. Carrollton"
          />
        </Field>
        <Field label="State">
          <select
            value={value.state}
            onChange={(e) => patch({ state: e.target.value })}
            className={INPUT_CLASS}
          >
            <option value="">—</option>
            {US_STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <Field
        label="Brief description"
        hint={`${descLen}/400 · what you make, hire for, or specialize in`}
      >
        <textarea
          rows={3}
          value={value.description}
          onChange={(e) => patch({ description: e.target.value.slice(0, 400) })}
          className={INPUT_CLASS}
          placeholder="e.g. Family-owned electrical contractor serving north Georgia since 1972…"
        />
      </Field>

      <div className="flex items-center justify-end gap-3 pt-1">
        <button
          type="submit"
          disabled={!valid}
          className="btn-lg disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Continue <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </form>
  );
}

function StepContact({
  value,
  onChange,
  email,
  onBack,
  onNext,
  valid,
  submitting,
}: {
  value: ContactForm;
  onChange: (v: ContactForm) => void;
  email: string | null;
  onBack: () => void;
  onNext: () => void;
  valid: boolean;
  submitting: boolean;
}) {
  const patch = (p: Partial<ContactForm>) => onChange({ ...value, ...p });
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid && !submitting) onNext();
      }}
    >
      <div>
        <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Verify your contact</h2>
        <p className="mt-1 text-caption text-slate">
          So candidates and the SKILLED Nation team can reach the right person.
        </p>
      </div>

      {email && (
        <div className="rounded-sm bg-stone px-3 py-2 text-caption text-slate">
          Signed in as <span className="font-medium text-cohere-ink">{email}</span>
        </div>
      )}

      <Field label="Hiring lead full name">
        <input
          required
          type="text"
          value={value.full_name}
          onChange={(e) => patch({ full_name: e.target.value })}
          className={INPUT_CLASS}
          placeholder="e.g. Jamie Rivera"
        />
      </Field>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Title" hint="Optional, e.g. Talent Acquisition Manager">
          <input
            type="text"
            value={value.contact_title}
            onChange={(e) => patch({ contact_title: e.target.value })}
            className={INPUT_CLASS}
            placeholder="e.g. Recruiting Manager"
          />
        </Field>
        <Field label="Phone" hint="Optional">
          <input
            type="tel"
            value={value.phone}
            onChange={(e) => patch({ phone: e.target.value })}
            className={INPUT_CLASS}
            placeholder="(555) 555-5555"
          />
        </Field>
      </div>

      <Field label="Timezone" hint="Auto-detected from your browser">
        <input
          type="text"
          value={value.timezone}
          onChange={(e) => patch({ timezone: e.target.value })}
          className={INPUT_CLASS}
        />
      </Field>

      <div className="flex items-center justify-between gap-3 pt-1">
        <button type="button" className="btn-ghost" onClick={onBack} disabled={submitting}>
          Back
        </button>
        <button
          type="submit"
          disabled={!valid || submitting}
          className="btn-lg disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {submitting ? "Saving…" : (
            <>
              Continue <ArrowRight className="h-4 w-4" />
            </>
          )}
        </button>
      </div>
    </form>
  );
}

function StepFirstJob() {
  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3">
        <CheckCircle2 className="mt-1 h-4 w-4 shrink-0 text-cohere-green" strokeWidth={1.75} />
        <div>
          <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Company profile saved</h2>
          <p className="mt-1 text-caption text-slate">
            Post your first job now to start receiving ranked candidate matches, or come back later.
          </p>
        </div>
      </div>

      <div className="rounded-sm border border-hairline bg-parchment p-5">
        <div className="flex items-start gap-3">
          <Briefcase className="mt-0.5 h-5 w-5 text-studio-maroon" strokeWidth={1.5} />
          <div>
            <p className="font-medium text-cohere-ink">Post your first job</p>
            <p className="mt-1 text-caption text-slate">
              Takes about 2 min. Matches begin appearing within a few minutes of posting.
            </p>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 pt-1">
        <a href="/employer" className="btn-link">
          Skip for now, I&apos;ll post later
        </a>
        <a href="/employer/jobs/new" className="btn-lg">
          Post your first job <ArrowRight className="h-4 w-4" />
        </a>
      </div>
    </div>
  );
}
