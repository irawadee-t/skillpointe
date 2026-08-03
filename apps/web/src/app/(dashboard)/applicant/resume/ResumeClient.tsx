"use client";

import { useState } from "react";
import Link from "next/link";
import { Sparkles, Download, Save, Loader2, FileText, Wand2 } from "lucide-react";

import { PageHeader, MonoLabel } from "@/components/ui";
import { ResumeUploader } from "@/components/applicant/ResumeUploader";
import { formatDate } from "@/lib/format";
import type { ResumeUpload } from "@/lib/api/robustness";
import {
  SummaryOut,
  generateSummary,
  saveSummary,
  downloadResume,
} from "@/lib/api/resume";

export function ResumeClient({
  initial,
  token,
  verifiedCount,
  latestUpload,
}: {
  initial: SummaryOut;
  token: string;
  verifiedCount: number;
  latestUpload?: ResumeUpload | null;
}) {
  // Current-file state for the uploader section. "Replace" swaps the compact
  // row for the full parse-review flow; a fresh parse updates the row.
  const [currentFile, setCurrentFile] = useState<{ filename: string; when: string | null } | null>(
    latestUpload ? { filename: latestUpload.filename, when: latestUpload.created_at } : null,
  );
  const [replacing, setReplacing] = useState(false);
  // Once a parse starts in this session, keep the uploader mounted so the
  // review step (field + certification checkboxes) and the done state stay
  // visible — the compact row would otherwise swap in mid-flow and eat them.
  const [inFlow, setInFlow] = useState(false);
  const [summary, setSummary] = useState(initial.summary ?? "");
  const [source, setSource] = useState(initial.source ?? (initial.summary ? "saved" : null));
  const [dirty, setDirty] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState(false);

  async function onGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const r = await generateSummary(token);
      setSummary(r.summary ?? "");
      setSource(r.source ?? "ai");
      setDirty(false);
    } catch {
      setError("Could not generate a summary. Please try again.");
    } finally {
      setGenerating(false);
    }
  }

  async function onSave() {
    if (!summary.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await saveSummary(token, summary.trim());
      setSource("manual");
      setDirty(false);
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 1800);
    } catch {
      setError("Could not save. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function onDownload() {
    setDownloading(true);
    setError(null);
    try {
      await downloadResume(token);
    } catch {
      setError("Could not download the résumé. Please try again.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <main className="py-8">
      <div className="page-shell max-w-3xl space-y-6">
        <PageHeader
          eyebrow="Your record"
          title="Résumé & summary"
          lead="Generate a professional summary from your verified profile, edit it in your own words, then export a one-page résumé that carries your SKILLED credentials."
          actions={
            <Link href="/applicant/credentials" className="btn-secondary">
              Credentials →
            </Link>
          }
        />

        {error && (
          <p className="rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">{error}</p>
        )}

        {/* Résumé file — upload + parse-review flow, with current-file state */}
        <section className="rounded-md border border-border-light bg-white p-5">
          <MonoLabel className="mb-3 flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" /> Résumé file
          </MonoLabel>
          {currentFile && !replacing && !inFlow ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="min-w-0 text-body text-cohere-ink">
                {currentFile.filename}
                {currentFile.when && (
                  <span className="text-slate-muted"> · uploaded {formatDate(currentFile.when)}</span>
                )}
              </p>
              <button onClick={() => setReplacing(true)} className="btn-secondary shrink-0">
                Replace
              </button>
            </div>
          ) : (
            <ResumeUploader
              token={token}
              onUploadedFile={(filename) => {
                setInFlow(true);
                setCurrentFile({ filename, when: new Date().toISOString() });
              }}
            />
          )}
        </section>

        {/* AI summary */}
        <section className="rounded-md border border-border-light bg-white p-5">
          <div className="flex items-center justify-between">
            <MonoLabel className="flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5" /> Profile summary
            </MonoLabel>
            {source && (
              <span className="inline-flex items-center rounded-full border border-hairline bg-white px-2 py-0.5 text-[11px] font-medium text-slate">
                {source === "ai" ? "AI-generated" : source === "template" ? "Auto-drafted" : source === "manual" ? "Edited by you" : "Saved"}
              </span>
            )}
          </div>

          <textarea
            value={summary}
            onChange={(e) => { setSummary(e.target.value); setDirty(true); }}
            rows={5}
            placeholder="Generate a summary from your verified profile, or write your own…"
            className="input-cohere mt-3 w-full resize-y leading-relaxed"
          />
          <p className="mt-1.5 text-micro text-slate-muted">
            Grounded strictly in your real profile and verified credentials. It never invents experience.
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button onClick={onGenerate} disabled={generating} className="btn-primary">
              {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
              {summary ? "Regenerate with AI" : "Generate with AI"}
            </button>
            <button onClick={onSave} disabled={saving || !dirty || !summary.trim()} className="btn-secondary">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {savedFlash ? "Saved" : "Save"}
            </button>
          </div>
        </section>

        {/* Résumé export */}
        <section className="rounded-md border border-cohere-green/25 bg-wash-green p-5">
          <MonoLabel className="flex items-center gap-1.5 text-cohere-green">
            <FileText className="h-3.5 w-3.5" /> One-page résumé
          </MonoLabel>
          <p className="mt-2 text-body text-cohere-green/90">
            Export a clean PDF with your summary and{" "}
            <strong>{verifiedCount} verified credential{verifiedCount === 1 ? "" : "s"}</strong>, each marked with its
            SKILLED verification tier.
          </p>
          <button onClick={onDownload} disabled={downloading} className="btn-primary mt-4">
            {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Download résumé PDF
          </button>
        </section>
      </div>
    </main>
  );
}
