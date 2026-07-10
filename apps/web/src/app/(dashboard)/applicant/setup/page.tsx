"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  ArrowRight, ArrowLeft, Check, Sparkles, MapPin, Briefcase, Plane, ShieldCheck, PartyPopper,
} from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import {
  US_STATES, CAREER_PATHS, PROGRAM_FIELDS, ENROLLMENT_STATUSES, DEGREE_TYPES,
  TRAVEL_OPTIONS, RELOCATION_OPTIONS,
} from "@/lib/constants";
import { SkilledNationLogo } from "@/components/ui/Logo";
import { easeCohere } from "@/lib/motion";
import { ResumeUploader } from "@/components/applicant/ResumeUploader";
import { Confetti } from "@/components/ui/Confetti";
import { fireOnce } from "@/lib/milestones";

const STEPS = [
  { n: 1, label: "About you", icon: Sparkles },
  { n: 2, label: "Your trade", icon: Briefcase },
  { n: 3, label: "Location & dates", icon: MapPin },
  { n: 4, label: "Mobility", icon: Plane },
];

function Label({ children, required }: { children: React.ReactNode; required?: boolean }) {
  return (
    <label className="mb-2 block text-caption font-medium text-slate">
      {children}{required && <span className="text-cohere-coral"> *</span>}
    </label>
  );
}

// Local-storage key for step-progress persistence.
// See item 16 in the UX audit: previously a partial failure kicked the user
// back to step 0 on reload, losing their place. We persist the completed step
// so a returning session (same browser) resumes where the user left off.
const SETUP_STEP_KEY = "applicant.setup.step";
const SETUP_FORM_KEY = "applicant.setup.form";

export default function ApplicantSetupPage() {
  const router = useRouter();
  const [step, _setStep] = useState(0); // 0 = welcome, 1-4 = form, 5 = done
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);

  // Wrap setStep so every step transition also persists to localStorage.
  const setStep = (next: number) => {
    _setStep(next);
    if (typeof window !== "undefined") {
      try {
        // Don't persist the terminal step 5 (done) so completed users don't
        // land back here on reload.
        if (next >= 1 && next <= 4) {
          window.localStorage.setItem(SETUP_STEP_KEY, String(next));
        } else if (next === 5 || next === 0) {
          window.localStorage.removeItem(SETUP_STEP_KEY);
          window.localStorage.removeItem(SETUP_FORM_KEY);
        }
      } catch { /* localStorage unavailable — silent */ }
    }
  };

  useEffect(() => {
    createClient().auth.getSession().then(({ data }) => setToken(data.session?.access_token ?? null));
    // Resume: rehydrate step + form draft from localStorage.
    if (typeof window !== "undefined") {
      try {
        const savedStep = window.localStorage.getItem(SETUP_STEP_KEY);
        const savedForm = window.localStorage.getItem(SETUP_FORM_KEY);
        if (savedForm) {
          const parsed = JSON.parse(savedForm) as Record<string, unknown>;
          setForm((prev) => ({ ...prev, ...parsed }));
        }
        if (savedStep) {
          const n = parseInt(savedStep, 10);
          if (n >= 1 && n <= 4) _setStep(n);
        }
      } catch { /* silent */ }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [form, setForm] = useState<Record<string, unknown>>({
    first_name: "", last_name: "", enrollment_status: "", degree_type: "", school_name: "",
    career_path: "", program_field: "", specific_career: "", program_name_raw: "",
    city: "", state: "", expected_completion_date: "", available_from_date: "",
    travel_preference: "within_state", relocation_preference: "stay_current",
    relocation_states: [] as string[],
  });
  const set = (field: string, value: unknown) => setForm((f) => {
    const next = { ...f, [field]: value };
    // Persist the in-flight draft so a mid-step reload doesn't wipe answers.
    if (typeof window !== "undefined") {
      try { window.localStorage.setItem(SETUP_FORM_KEY, JSON.stringify(next)); }
      catch { /* silent */ }
    }
    return next;
  });

  const filteredPrograms = useMemo(
    () => (!form.career_path ? PROGRAM_FIELDS : PROGRAM_FIELDS.filter((p) => p.careerPath === form.career_path)),
    [form.career_path],
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { router.push("/login"); return; }

    const payload: Record<string, unknown> = { ...form, onboarding_complete: true };
    payload.willing_to_travel = payload.travel_preference !== "no_travel";
    payload.willing_to_relocate = payload.relocation_preference !== "stay_current";
    for (const key of Object.keys(payload)) {
      if (payload[key] === "" || payload[key] === null) delete payload[key];
    }
    const resp = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/applicant/me/profile`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${session.access_token}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      setError(err.detail ?? "Something went wrong. Please try again.");
      setLoading(false);
      return;
    }
    setLoading(false);
    setStep(5);
  }

  const firstName = (form.first_name as string) || "";

  return (
    <main className="min-h-[calc(100vh-4rem)]">
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl gap-0 lg:grid-cols-[300px_1fr]">
        {/* Progress rail */}
        <aside className="hidden flex-col justify-between border-r border-hairline bg-canvas-soft p-10 lg:flex">
          <div>
            <SkilledNationLogo width={132} />
            <p className="mt-8 font-display text-card leading-tight text-cohere-ink">
              {step === 0 ? "Let's build your profile." : step === 5 ? "You're all set." : "Almost there."}
            </p>
            <p className="mt-2 text-body text-slate">About three minutes — then employers can find you.</p>
            <ol className="mt-10 space-y-1">
              {STEPS.map((s) => {
                const done = step > s.n || step === 5;
                const active = step === s.n;
                return (
                  <li key={s.n} className="flex items-center gap-3 py-2">
                    <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-caption ${
                      done ? "border-cohere-green bg-cohere-green text-white"
                        : active ? "border-cohere-ink text-cohere-ink"
                        : "border-hairline text-slate-muted"}`}>
                      {done ? <Check className="h-3.5 w-3.5" /> : s.n}
                    </span>
                    <span className={`text-body ${active ? "font-medium text-cohere-ink" : done ? "text-slate" : "text-slate-muted"}`}>
                      {s.label}
                    </span>
                  </li>
                );
              })}
            </ol>
          </div>
          <p className="text-micro text-slate-muted">You can change all of this later from your profile.</p>
        </aside>

        {/* Step content */}
        <section className="flex items-center justify-center px-5 py-12 sm:px-12">
          <div className="w-full max-w-xl">
            {/* mobile progress */}
            {step >= 1 && step <= 4 && (
              <div className="mb-8 flex gap-1.5 lg:hidden">
                {STEPS.map((s) => (
                  <div key={s.n} className={`h-1.5 flex-1 rounded-full ${step > s.n ? "bg-cohere-green" : step === s.n ? "bg-studio-dark-cork" : "bg-hairline"}`} />
                ))}
              </div>
            )}

            <AnimatePresence mode="wait">
              <motion.div
                key={step}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.35, ease: easeCohere }}
              >
                {/* ---- Welcome ---- */}
                {step === 0 && (
                  <div>
                    <span className="mono-label text-cohere-coral">Welcome to SKILLED Nation</span>
                    <h1 className="mt-4 font-display text-heading leading-[1.05] text-cohere-ink">
                      Get discovered for the work you're trained to do.
                    </h1>
                    <p className="mt-4 text-body-lg text-slate">
                      Tell us about your trade, where you are, and how far you'll go. We'll rank real jobs for
                      you, explain every match, and let you control who sees your verified record.
                    </p>

                    {token && (
                      <div className="mt-8 space-y-3">
                        <p className="text-caption text-slate">
                          Upload a resume and we&apos;ll parse it in a few seconds — then you&apos;ll continue to step 1 with your fields already filled in.
                        </p>
                        <ResumeUploader token={token} onApplied={(fields) => {
                          setForm((prev) => ({ ...prev, ...fields }));
                          // Auto-advance to step 1 once the resume is applied.
                          setStep(1);
                        }} />
                      </div>
                    )}

                    <button onClick={() => setStep(1)} className="btn-primary mt-6 inline-flex items-center gap-2">
                      {form.first_name ? "Continue to step 1" : "Skip and enter manually"} <ArrowRight className="h-4 w-4" />
                    </button>
                  </div>
                )}

                {/* ---- Step 1: About you ---- */}
                {step === 1 && (
                  <form onSubmit={(e) => { e.preventDefault(); setStep(2); }} className="space-y-5">
                    <StepHead>About you</StepHead>
                    <div className="grid grid-cols-2 gap-4">
                      <div><Label required>First name</Label><input value={form.first_name as string} onChange={(e) => set("first_name", e.target.value)} required className="input-cohere" placeholder="Jane" /></div>
                      <div><Label required>Last name</Label><input value={form.last_name as string} onChange={(e) => set("last_name", e.target.value)} required className="input-cohere" placeholder="Smith" /></div>
                    </div>
                    <div><Label>Current enrollment</Label>
                      <select value={form.enrollment_status as string} onChange={(e) => set("enrollment_status", e.target.value)} className="input-cohere">
                        <option value="">Select…</option>{ENROLLMENT_STATUSES.map((e) => <option key={e.value} value={e.value}>{e.label}</option>)}
                      </select>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div><Label>Degree type</Label>
                        <select value={form.degree_type as string} onChange={(e) => set("degree_type", e.target.value)} className="input-cohere">
                          <option value="">Select…</option>{DEGREE_TYPES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                        </select>
                      </div>
                      <div><Label>School</Label><input value={form.school_name as string} onChange={(e) => set("school_name", e.target.value)} className="input-cohere" placeholder="Penn College" /></div>
                    </div>
                    <NavRow onBack={() => setStep(0)} nextLabel="Continue" />
                  </form>
                )}

                {/* ---- Step 2: Your trade ---- */}
                {step === 2 && (
                  <form onSubmit={(e) => { e.preventDefault(); if (form.career_path) setStep(3); }} className="space-y-5">
                    <StepHead>What's your trade?</StepHead>
                    <p className="-mt-2 text-body text-slate">Pick the path that fits best — this drives your matches.</p>
                    <div className="grid grid-cols-2 gap-3">
                      {CAREER_PATHS.map((c) => {
                        const selected = form.career_path === c.value;
                        return (
                          <button key={c.value} type="button"
                            onClick={() => { set("career_path", c.value); set("program_field", ""); }}
                            className={`rounded-xl border p-4 text-left transition-all ${
                              selected ? "border-cohere-green bg-wash-green shadow-[0_1px_2px_rgba(12,10,9,0.04)]"
                                : "border-hairline bg-white hover:border-cohere-ink"}`}>
                            <span className={`text-body font-medium ${selected ? "text-cohere-green" : "text-cohere-ink"}`}>{c.label}</span>
                            {selected && <Check className="float-right h-4 w-4 text-cohere-green" />}
                          </button>
                        );
                      })}
                    </div>
                    {Boolean(form.career_path) && (
                      <div className="space-y-4 border-t border-hairline pt-4">
                        <div><Label>Program / field</Label>
                          <select value={form.program_field as string} onChange={(e) => set("program_field", e.target.value)} className="input-cohere">
                            <option value="">Select…</option>{filteredPrograms.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                          </select>
                        </div>
                        <div><Label>Specific program or role</Label>
                          <input value={form.specific_career as string} onChange={(e) => set("specific_career", e.target.value)} className="input-cohere" placeholder="e.g. A.A.S. Building Construction" />
                        </div>
                      </div>
                    )}
                    <NavRow onBack={() => setStep(1)} nextLabel="Continue" disabled={!form.career_path} />
                  </form>
                )}

                {/* ---- Step 3: Location & dates ---- */}
                {step === 3 && (
                  <form onSubmit={(e) => { e.preventDefault(); setStep(4); }} className="space-y-5">
                    <StepHead>Where & when</StepHead>
                    <div className="grid grid-cols-2 gap-4">
                      <div><Label>City</Label><input value={form.city as string} onChange={(e) => set("city", e.target.value)} className="input-cohere" placeholder="Williamsport" /></div>
                      <div><Label>State</Label>
                        <select value={form.state as string} onChange={(e) => set("state", e.target.value)} className="input-cohere">
                          <option value="">Select</option>{US_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div><Label>Program completion</Label><input type="date" value={form.expected_completion_date as string} onChange={(e) => set("expected_completion_date", e.target.value)} className="input-cohere" /></div>
                      <div><Label>Available to start</Label><input type="date" value={form.available_from_date as string} onChange={(e) => set("available_from_date", e.target.value)} className="input-cohere" /></div>
                    </div>
                    <NavRow onBack={() => setStep(2)} nextLabel="Continue" />
                  </form>
                )}

                {/* ---- Step 4: Mobility ---- */}
                {step === 4 && (
                  <form onSubmit={handleSubmit} className="space-y-6">
                    <StepHead>How far will you go?</StepHead>
                    <div>
                      <Label>Travel for work</Label>
                      <div className="space-y-2">
                        {TRAVEL_OPTIONS.map((opt) => (
                          <Choice key={opt.value} selected={form.travel_preference === opt.value} onSelect={() => set("travel_preference", opt.value)} label={opt.label} desc={opt.desc} />
                        ))}
                      </div>
                    </div>
                    <div>
                      <Label>Relocation</Label>
                      <div className="space-y-2">
                        {RELOCATION_OPTIONS.map((opt) => (
                          <Choice key={opt.value} selected={form.relocation_preference === opt.value} onSelect={() => set("relocation_preference", opt.value)} label={opt.label} desc={opt.desc} />
                        ))}
                      </div>
                    </div>
                    {form.relocation_preference === "specific_states" && (
                      <div>
                        <Label>Which states?</Label>
                        <div className="grid max-h-44 grid-cols-6 gap-1.5 overflow-y-auto rounded-md border border-hairline p-3 sm:grid-cols-8">
                          {US_STATES.map((s) => {
                            const sel = ((form.relocation_states as string[]) || []).includes(s);
                            return (
                              <button key={s} type="button" onClick={() => {
                                const cur = (form.relocation_states as string[]) || [];
                                set("relocation_states", sel ? cur.filter((x) => x !== s) : [...cur, s]);
                              }} className={`rounded-sm py-1.5 text-micro transition-colors ${sel ? "bg-studio-dark-cork font-medium text-white" : "bg-stone text-slate hover:bg-hairline"}`}>{s}</button>
                            );
                          })}
                        </div>
                      </div>
                    )}
                    {error && <p className="rounded-md border border-cohere-coral-soft bg-cohere-coral/10 p-3 text-body text-error-red">{error}</p>}
                    <NavRow onBack={() => setStep(3)} nextLabel={loading ? "Saving…" : "Finish setup"} disabled={loading} submit />
                  </form>
                )}

                {/* ---- Done ---- */}
                {step === 5 && (
                  <DoneStep firstName={firstName} onSeeMatches={() => { router.push("/applicant/matches"); router.refresh(); }} onAddCredential={() => { router.push("/applicant/credentials"); router.refresh(); }} />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </section>
      </div>
    </main>
  );
}

function StepHead({ children }: { children: React.ReactNode }) {
  return <h1 className="font-display text-card leading-tight text-cohere-ink">{children}</h1>;
}

function NavRow({ onBack, nextLabel, disabled, submit }: { onBack: () => void; nextLabel: string; disabled?: boolean; submit?: boolean }) {
  return (
    <div className="flex items-center justify-between pt-2">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1.5 text-body text-slate transition-colors hover:text-cohere-ink">
        <ArrowLeft className="h-4 w-4" /> Back
      </button>
      <button type={submit ? "submit" : "submit"} disabled={disabled} className="btn-primary inline-flex items-center gap-2 disabled:opacity-50">
        {nextLabel} <ArrowRight className="h-4 w-4" />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Done step — Confetti burst + auto-route to matches after 2.5s if the user
// hasn't picked the "Add a credential" path. Kept as its own component so
// we can own timer + celebration lifecycle without cluttering the main body.
// ---------------------------------------------------------------------------
function DoneStep({ firstName, onSeeMatches, onAddCredential }: {
  firstName: string;
  onSeeMatches: () => void;
  onAddCredential: () => void;
}) {
  const [confetti, setConfetti] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [countdown, setCountdown] = useState(3);

  useEffect(() => {
    // One-time confetti — even a returning user who hits step 5 twice only
    // sees the burst once.
    if (fireOnce("first_setup_complete")) setConfetti(true);
  }, []);

  useEffect(() => {
    if (cancelled) return;
    if (countdown <= 0) { onSeeMatches(); return; }
    const t = setTimeout(() => setCountdown((c) => c - 1), 833); // ~2.5s total
    return () => clearTimeout(t);
  }, [countdown, cancelled, onSeeMatches]);

  return (
    <div className="text-center">
      <Confetti active={confetti} />
      <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-wash-green">
        <PartyPopper className="h-7 w-7 text-cohere-green" />
      </div>
      <h1 className="mt-6 font-display text-heading leading-tight text-cohere-ink">
        You're on the map{firstName ? `, ${firstName}` : ""}.
      </h1>
      <p className="mx-auto mt-3 max-w-md text-body-lg text-slate">
        We're ranking jobs for you right now. Add a credential to get verified and rise in employer search.
      </p>
      <div className="mt-8 flex justify-center gap-3">
        <button onClick={onSeeMatches} className="btn-primary inline-flex items-center gap-2">
          See my matches <ArrowRight className="h-4 w-4" />
        </button>
        <button
          onClick={() => { setCancelled(true); onAddCredential(); }}
          className="btn-pill-outline inline-flex items-center gap-2"
        >
          <ShieldCheck className="h-4 w-4" /> Add a credential
        </button>
      </div>
      {!cancelled && (
        <p className="mt-4 text-caption text-slate-muted">
          Redirecting to your matches in {countdown}…{" "}
          <button
            type="button"
            onClick={() => setCancelled(true)}
            className="underline decoration-hairline underline-offset-2 hover:text-cohere-ink"
          >
            stay here
          </button>
        </p>
      )}
    </div>
  );
}

function Choice({ selected, onSelect, label, desc }: { selected: boolean; onSelect: () => void; label: string; desc: string }) {
  return (
    <button type="button" onClick={onSelect}
      className={`flex w-full items-start gap-3 rounded-xl border p-3.5 text-left transition-colors ${
        selected ? "border-cohere-green bg-wash-green" : "border-hairline bg-white hover:border-cohere-ink"}`}>
      <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${selected ? "border-cohere-green bg-cohere-green" : "border-hairline"}`}>
        {selected && <Check className="h-2.5 w-2.5 text-white" />}
      </span>
      <span>
        <span className="text-body font-medium text-cohere-ink">{label}</span>
        <span className="block text-caption text-slate">{desc}</span>
      </span>
    </button>
  );
}
