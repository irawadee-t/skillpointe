"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { createClient } from "@/lib/supabase/client";
import {
  US_STATES,
  CAREER_PATHS,
  PROGRAM_FIELDS,
  ENROLLMENT_STATUSES,
  DEGREE_TYPES,
  TRAVEL_OPTIONS,
  RELOCATION_OPTIONS,
} from "@/lib/constants";

export default function ApplicantSetupPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState<Record<string, unknown>>({
    first_name: "",
    last_name: "",
    enrollment_status: "",
    degree_type: "",
    school_name: "",
    career_path: "",
    program_field: "",
    specific_career: "",
    program_name_raw: "",
    city: "",
    state: "",
    expected_completion_date: "",
    available_from_date: "",
    travel_preference: "within_state",
    relocation_preference: "stay_current",
    relocation_states: [] as string[],
  });

  function set(field: string, value: unknown) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  const filteredPrograms = useMemo(() => {
    if (!form.career_path) return PROGRAM_FIELDS;
    return PROGRAM_FIELDS.filter((p) => p.careerPath === form.career_path);
  }, [form.career_path]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const supabase = createClient();
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) { router.push("/login"); return; }

    const payload: Record<string, unknown> = { ...form, onboarding_complete: true };
    // Derive legacy booleans
    payload.willing_to_travel = payload.travel_preference !== "no_travel";
    payload.willing_to_relocate = payload.relocation_preference !== "stay_current";
    // Clean empties
    for (const key of Object.keys(payload)) {
      if (payload[key] === "" || payload[key] === null) delete payload[key];
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

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      setError(err.detail ?? "Something went wrong. Please try again.");
      setLoading(false);
      return;
    }

    router.push("/applicant");
    router.refresh();
  }

  const TOTAL_STEPS = 4;
  const stepLabel = ["", "Basic info", "Your program", "Location & dates", "Travel & relocation"][step];

  return (
    <main className="flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-white">Set up your profile</h1>
          <p className="text-sm text-zinc-400 mt-1">
            Step {step} of {TOTAL_STEPS} &mdash; {stepLabel}
          </p>
          <div className="flex gap-2 mt-4 justify-center">
            {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
              <div key={i} className={`h-1.5 w-12 rounded-full transition-colors ${step > i ? "bg-cyan-500" : step === i + 1 ? "bg-white" : "bg-zinc-700"}`} />
            ))}
          </div>
        </div>

        <div className="bg-zinc-900 rounded-lg border border-zinc-800 p-8">

          {/* ---- Step 1: Basic Info ---- */}
          {step === 1 && (
            <form onSubmit={(e) => { e.preventDefault(); setStep(2); }} className="space-y-5">
              <h2 className="font-semibold text-white mb-4">About you</h2>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-1">First name <span className="text-rose-400">*</span></label>
                  <input type="text" value={form.first_name as string} onChange={(e) => set("first_name", e.target.value)} required className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500" placeholder="Jane" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-1">Last name <span className="text-rose-400">*</span></label>
                  <input type="text" value={form.last_name as string} onChange={(e) => set("last_name", e.target.value)} required className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500" placeholder="Smith" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Current enrollment</label>
                <select value={form.enrollment_status as string} onChange={(e) => set("enrollment_status", e.target.value)} className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500">
                  <option value="">Select...</option>
                  {ENROLLMENT_STATUSES.map((e) => <option key={e.value} value={e.value}>{e.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Degree type</label>
                <select value={form.degree_type as string} onChange={(e) => set("degree_type", e.target.value)} className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500">
                  <option value="">Select...</option>
                  {DEGREE_TYPES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">School name</label>
                <input type="text" value={form.school_name as string} onChange={(e) => set("school_name", e.target.value)} className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500" placeholder="e.g. Penn College of Technology" />
              </div>
              <button type="submit" className="w-full bg-cyan-500 text-black py-2.5 rounded-full text-sm font-medium hover:bg-cyan-400 transition-colors">
                Next &rarr;
              </button>
            </form>
          )}

          {/* ---- Step 2: Program & Career ---- */}
          {step === 2 && (
            <form onSubmit={(e) => { e.preventDefault(); setStep(3); }} className="space-y-5">
              <h2 className="font-semibold text-white mb-4">Your program</h2>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Career path <span className="text-rose-400">*</span></label>
                <select value={form.career_path as string} onChange={(e) => { set("career_path", e.target.value); set("program_field", ""); }} required className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500">
                  <option value="">Select a career path...</option>
                  {CAREER_PATHS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Program / field of study</label>
                <select value={form.program_field as string} onChange={(e) => set("program_field", e.target.value)} className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500">
                  <option value="">Select...</option>
                  {filteredPrograms.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-1">Specific career or program name</label>
                <input type="text" value={form.specific_career as string} onChange={(e) => set("specific_career", e.target.value)} className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500" placeholder="e.g. A.A.S. Building Construction Technologies" />
                <p className="text-xs text-zinc-500 mt-1">Describe exactly what you study or want to do</p>
              </div>
              <div className="flex gap-3 pt-1">
                <button type="button" onClick={() => setStep(1)} className="flex-1 border border-zinc-700 text-zinc-300 py-2.5 rounded-full text-sm font-medium hover:border-zinc-500 hover:text-white transition-colors">&larr; Back</button>
                <button type="submit" className="flex-1 bg-cyan-500 text-black py-2.5 rounded-full text-sm font-medium hover:bg-cyan-400 transition-colors">Next &rarr;</button>
              </div>
            </form>
          )}

          {/* ---- Step 3: Location & Dates ---- */}
          {step === 3 && (
            <form onSubmit={(e) => { e.preventDefault(); setStep(4); }} className="space-y-5">
              <h2 className="font-semibold text-white mb-4">Location &amp; availability</h2>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-1">City</label>
                  <input type="text" value={form.city as string} onChange={(e) => set("city", e.target.value)} className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500" placeholder="Williamsport" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-1">State</label>
                  <select value={form.state as string} onChange={(e) => set("state", e.target.value)} className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500">
                    <option value="">Select state</option>
                    {US_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-1">Expected completion date</label>
                  <input type="date" value={form.expected_completion_date as string} onChange={(e) => set("expected_completion_date", e.target.value)} className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-1">Available to start work</label>
                  <input type="date" value={form.available_from_date as string} onChange={(e) => set("available_from_date", e.target.value)} className="w-full border border-zinc-700 rounded-lg px-3 py-2 text-sm bg-zinc-900 text-white focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500" />
                </div>
              </div>
              <div className="flex gap-3 pt-1">
                <button type="button" onClick={() => setStep(2)} className="flex-1 border border-zinc-700 text-zinc-300 py-2.5 rounded-full text-sm font-medium hover:border-zinc-500 hover:text-white transition-colors">&larr; Back</button>
                <button type="submit" className="flex-1 bg-cyan-500 text-black py-2.5 rounded-full text-sm font-medium hover:bg-cyan-400 transition-colors">Next &rarr;</button>
              </div>
            </form>
          )}

          {/* ---- Step 4: Travel & Relocation ---- */}
          {step === 4 && (
            <form onSubmit={handleSubmit} className="space-y-5">
              <h2 className="font-semibold text-white mb-4">Travel &amp; relocation</h2>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">Willingness to travel for work</label>
                <div className="space-y-2">
                  {TRAVEL_OPTIONS.map((opt) => (
                    <label key={opt.value} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${form.travel_preference === opt.value ? "border-cyan-500 bg-cyan-500/10" : "border-zinc-700 hover:border-zinc-500"}`}>
                      <input type="radio" name="travel" value={opt.value} checked={form.travel_preference === opt.value} onChange={() => set("travel_preference", opt.value)} className="mt-0.5 accent-cyan-500" />
                      <div>
                        <span className="text-sm font-medium text-white">{opt.label}</span>
                        <p className="text-xs text-zinc-400">{opt.desc}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">Willingness to relocate</label>
                <div className="space-y-2">
                  {RELOCATION_OPTIONS.map((opt) => (
                    <label key={opt.value} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${form.relocation_preference === opt.value ? "border-cyan-500 bg-cyan-500/10" : "border-zinc-700 hover:border-zinc-500"}`}>
                      <input type="radio" name="relocation" value={opt.value} checked={form.relocation_preference === opt.value} onChange={() => set("relocation_preference", opt.value)} className="mt-0.5 accent-cyan-500" />
                      <div>
                        <span className="text-sm font-medium text-white">{opt.label}</span>
                        <p className="text-xs text-zinc-400">{opt.desc}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              {form.relocation_preference === "specific_states" && (
                <div>
                  <label className="block text-sm font-medium text-zinc-300 mb-2">Which states?</label>
                  <div className="grid grid-cols-5 sm:grid-cols-8 gap-1.5 max-h-48 overflow-y-auto border border-zinc-700 rounded-lg p-3">
                    {US_STATES.map((s) => {
                      const selected = ((form.relocation_states as string[]) || []).includes(s);
                      return (
                        <button key={s} type="button" onClick={() => {
                          const cur = (form.relocation_states as string[]) || [];
                          set("relocation_states", selected ? cur.filter((x) => x !== s) : [...cur, s]);
                        }} className={`text-xs font-mono py-1.5 rounded transition-colors ${selected ? "bg-cyan-500 text-black font-medium" : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"}`}>{s}</button>
                      );
                    })}
                  </div>
                </div>
              )}

              {error && <p className="text-sm text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded-lg p-3">{error}</p>}

              <div className="flex gap-3 pt-1">
                <button type="button" onClick={() => setStep(3)} className="flex-1 border border-zinc-700 text-zinc-300 py-2.5 rounded-full text-sm font-medium hover:border-zinc-500 hover:text-white transition-colors">&larr; Back</button>
                <button type="submit" disabled={loading} className="flex-1 bg-cyan-500 text-black py-2.5 rounded-full text-sm font-medium hover:bg-cyan-400 disabled:opacity-50 transition-colors">
                  {loading ? "Saving..." : "Complete setup"}
                </button>
              </div>
            </form>
          )}
        </div>

        <p className="mt-4 text-center text-xs text-zinc-500">
          You can update all of this later from your profile.
        </p>
      </div>
    </main>
  );
}
