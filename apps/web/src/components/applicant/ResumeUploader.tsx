"use client";

import { useState } from "react";
import Link from "next/link";
import { UploadCloud, Loader2, Check, X, Sparkles, Camera, BadgeCheck } from "lucide-react";

import { ParsedResume, applyResume, parseResume } from "@/lib/api/robustness";
import { addCredential } from "@/lib/api/credentials";
import { MonoLabel } from "@/components/ui";

const FIELD_LABELS: Record<string, string> = {
  first_name:       "First name",
  last_name:        "Last name",
  phone:            "Phone",
  email:            "Email",
  city:             "City",
  state:            "State",
  program_name_raw: "Program / trade",
  career_goals_raw: "Career goals",
  experience_raw:   "Experience",
  bio_raw:          "Bio",
  years_experience: "Years of experience",
};

export function ResumeUploader({
  token, onApplied, onUploadedFile,
}: {
  token: string;
  onApplied?: (fields: Record<string, unknown>) => void;
  /** Fires when a file parses successfully — lets the page show current-file state. */
  onUploadedFile?: (filename: string) => void;
}) {
  const [status, setStatus] = useState<"idle" | "uploading" | "parsed" | "applying" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const [parsed, setParsed] = useState<ParsedResume | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  // Parsed-certifications bridge: checked items become self-reported
  // credentials via the credentials API (canonical normalization runs
  // server-side); the credentials page then shows the standard verify
  // affordance on each new row.
  const [selectedCerts, setSelectedCerts] = useState<Record<string, boolean>>({});
  const [certsAdded, setCertsAdded] = useState(0);
  const [certsFailed, setCertsFailed] = useState(0);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return;
    setStatus("uploading"); setError(null); setParsed(null);
    try {
      const p = await parseResume(token, f);
      setParsed(p);
      const s: Record<string, boolean> = {};
      for (const k of Object.keys(p.fields)) s[k] = true;
      setSelected(s);
      const certs: Record<string, boolean> = {};
      for (const c of p.certifications) certs[c] = true;
      setSelectedCerts(certs);
      setStatus("parsed");
      onUploadedFile?.(f.name);
    } catch (err: unknown) {
      setStatus("idle");
      setError(err instanceof Error ? err.message : "Could not read that file.");
    }
  }

  async function apply() {
    if (!parsed) return;
    setStatus("applying"); setError(null);
    const accept: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(parsed.fields)) {
      if (selected[k] && v !== undefined && v !== null && v !== "") accept[k] = v;
    }
    try {
      await applyResume(token, parsed.upload_id, accept);
    } catch (err: unknown) {
      setStatus("parsed");
      setError(err instanceof Error ? err.message : "Could not save.");
      return;
    }
    // Create self-reported credentials for the checked certifications.
    const certs = parsed.certifications.filter((c) => selectedCerts[c]);
    let added = 0;
    let failed = 0;
    for (const c of certs) {
      try {
        await addCredential(token, { raw_name: c, category: "certification" });
        added++;
      } catch {
        failed++;
      }
    }
    setCertsAdded(added);
    setCertsFailed(failed);
    setStatus("done");
    onApplied?.(accept);
  }

  if (status === "done") {
    return (
      <div className="rounded-xl border border-cohere-green/30 bg-wash-green p-5 text-body text-cohere-ink">
        <p>
          <Check className="mr-1.5 inline h-4 w-4 text-cohere-green" />
          Done. The selected fields were saved to your profile.
        </p>
        {certsAdded > 0 && (
          <p className="mt-2 flex items-start gap-1.5 text-caption">
            <BadgeCheck className="mt-0.5 h-4 w-4 shrink-0 text-cohere-green" />
            <span>
              {certsAdded} credential{certsAdded === 1 ? "" : "s"} added from your résumé.{" "}
              <Link href="/applicant/credentials" className="font-medium underline">
                Verify them to strengthen matches →
              </Link>
            </span>
          </p>
        )}
        {certsFailed > 0 && (
          <p className="mt-1.5 text-caption text-slate">
            {certsFailed} certification{certsFailed === 1 ? "" : "s"} couldn&apos;t be added. You can
            add {certsFailed === 1 ? "it" : "them"} by hand on the credentials page.
          </p>
        )}
      </div>
    );
  }

  if (status === "idle" || status === "uploading") {
    return (
      <div className="rounded-xl border-2 border-dashed border-hairline bg-white p-6 text-center transition-colors hover:border-cohere-green">
        {status === "uploading" ? (
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-cohere-green" />
        ) : (
          <UploadCloud className="mx-auto h-8 w-8 text-slate-muted" strokeWidth={1.5} />
        )}
        <div className="mt-3 font-medium text-cohere-ink">
          {status === "uploading" ? "Reading your resume…" : "Upload your resume"}
        </div>
        <div className="mt-1 text-caption text-slate">
          PDF, DOCX, or TXT. We&apos;ll pull out what we can. You review before it saves.
        </div>

        <div className="mt-4 flex flex-col items-center justify-center gap-2 sm:flex-row">
          <label className="btn-primary inline-flex cursor-pointer items-center gap-1.5">
            <UploadCloud className="h-4 w-4" />
            Choose file
            <input type="file" accept=".pdf,.docx,.txt,application/pdf,image/*" onChange={onFile}
              className="hidden" disabled={status === "uploading"} />
          </label>
          {/* Native camera capture on phones — falls back to file picker on desktop. */}
          <label className="btn-pill-outline inline-flex cursor-pointer items-center gap-1.5 sm:hidden">
            <Camera className="h-4 w-4" />
            Take photo
            <input type="file" accept="image/*" capture="environment" onChange={onFile}
              className="hidden" disabled={status === "uploading"} />
          </label>
        </div>

        {error && <p className="mt-3 text-caption text-studio-maroon">{error}</p>}
      </div>
    );
  }

  // parsed / applying
  if (!parsed) return null;
  const shownFields = Object.entries(parsed.fields).filter(([, v]) => v !== undefined && v !== null && v !== "");
  const checkedCertCount = parsed.certifications.filter((c) => selectedCerts[c]).length;
  return (
    <div className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
      <div className="flex items-center gap-2">
        <Sparkles className="h-5 w-5 text-cohere-green" strokeWidth={1.75} />
        <h3 className="text-[1.0625rem] font-medium text-cohere-ink">Here&apos;s what we read</h3>
      </div>
      <p className="mt-1 text-caption text-slate">
        Uncheck anything that looks wrong. You can also edit each field after it&apos;s saved.
      </p>

      {error && <div className="mt-3 rounded-md border border-studio-maroon/30 bg-studio-maroon/[0.06] p-3 text-caption">{error}</div>}

      <div className="mt-4 grid gap-2">
        {shownFields.length === 0 && (
          <p className="text-caption text-slate-muted">
            We couldn&apos;t extract standard fields from this file. You can still edit your profile by hand below.
          </p>
        )}
        {shownFields.map(([k, v]) => (
          <label key={k} className="flex items-start gap-3 rounded-md border border-hairline bg-stone/40 px-3 py-2">
            <input type="checkbox"
              checked={selected[k] ?? false}
              onChange={(e) => setSelected((s) => ({ ...s, [k]: e.target.checked }))}
              className="mt-1 accent-cohere-green" />
            <div className="flex-1">
              <MonoLabel className="mb-0.5 block">{FIELD_LABELS[k] ?? k}</MonoLabel>
              <div className="text-caption text-cohere-ink whitespace-pre-line line-clamp-3">{String(v)}</div>
            </div>
          </label>
        ))}
      </div>

      {(parsed.certifications.length > 0 || parsed.skills.length > 0) && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {parsed.certifications.length > 0 && (
            <div>
              <MonoLabel className="mb-1.5 block">Certifications found: add to your credentials</MonoLabel>
              <div className="grid gap-1.5">
                {parsed.certifications.map((c) => (
                  <label key={c} className="flex items-center gap-2 text-caption text-cohere-ink">
                    <input
                      type="checkbox"
                      checked={selectedCerts[c] ?? false}
                      onChange={(e) => setSelectedCerts((s) => ({ ...s, [c]: e.target.checked }))}
                      className="accent-cohere-green"
                    />
                    {c}
                  </label>
                ))}
              </div>
              <p className="mt-1.5 text-micro text-slate-muted">
                Checked items are saved as self-reported credentials. You can attach proof to
                verify them afterwards.
              </p>
            </div>
          )}
          {parsed.skills.length > 0 && (
            <div>
              <MonoLabel className="mb-1.5 block">Skills found</MonoLabel>
              <div className="flex flex-wrap gap-1.5">
                {parsed.skills.slice(0, 12).map((s) => (
                  <span key={s} className="inline-flex items-center rounded-full border border-hairline bg-white px-2 py-0.5 text-[11px] font-medium text-slate">{s}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="mt-5 flex items-center justify-end gap-2">
        <button onClick={() => { setParsed(null); setStatus("idle"); }} className="btn-pill-outline">
          <X className="h-4 w-4" /> Discard
        </button>
        <button
          onClick={apply}
          disabled={status === "applying" || (shownFields.length === 0 && checkedCertCount === 0)}
          className="btn-primary inline-flex items-center gap-1.5"
        >
          {status === "applying" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          Save to my profile
        </button>
      </div>
    </div>
  );
}
