"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Link2, FileSpreadsheet, FileText, Plus, Loader2, ArrowRight,
  CheckCircle2, AlertTriangle, Edit3, X, Send, Eye,
} from "lucide-react";

import {
  BatchDetail, ImportRow,
  importFromUrl, importFromCsv, importManual, submitBatch, editRow, excludeRow,
} from "@/lib/api/jobImports";
import { PageHeader, MonoLabel } from "@/components/ui";

type Mode = "picker" | "url" | "csv" | "manual" | "preview";

const CSV_TEMPLATE = `title,city,state,description,requirements,pay_min,pay_max,pay_type,experience_level,source_url
Welder I,Carrollton,GA,"Work in our facility welding steel components.","High-school diploma; 1+ year welding.",22,28,hourly,entry,https://example.com/welder-i
Industrial Electrician,Atlanta,GA,"Maintain and repair electrical systems in a manufacturing plant.","Journeyman electrician license; 3+ years in industrial settings.",35,42,hourly,mid,https://example.com/electrician`;

export function ImportClient({ token }: { token: string }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("picker");
  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Add jobs"
          title="Import jobs"
          lead="Paste a careers URL, upload a spreadsheet, or enter jobs by hand. You'll preview every row before submitting to SKILLED admins for approval — once approved, jobs go live to ranked workers."
          actions={
            <Link href="/employer/jobs/imports/list" className="btn-pill-outline inline-flex items-center gap-1">
              <Eye className="h-4 w-4" /> My batches
            </Link>
          }
        />

        {error && (
          <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4 text-body text-cohere-ink">
            <AlertTriangle className="inline h-4 w-4 mr-1.5 text-studio-maroon" />{error}
          </div>
        )}

        {mode === "picker" && !batch && <ModePicker onPick={setMode} />}

        {mode === "url" && !batch && (
          <UrlMode token={token} loading={loading} setLoading={setLoading}
            onError={setError} onParsed={(b) => { setBatch(b); setMode("preview"); }}
            onBack={() => setMode("picker")}
            onSwitchToCsv={() => { setError(null); setMode("csv"); }} />
        )}

        {mode === "csv" && !batch && (
          <CsvMode token={token} loading={loading} setLoading={setLoading}
            onError={setError} onParsed={(b) => { setBatch(b); setMode("preview"); }}
            onBack={() => setMode("picker")} />
        )}

        {mode === "manual" && !batch && (
          <ManualMode token={token} loading={loading} setLoading={setLoading}
            onError={setError} onParsed={(b) => { setBatch(b); setMode("preview"); }}
            onBack={() => setMode("picker")} />
        )}

        {batch && (
          <PreviewBatch
            token={token} batch={batch}
            onRefresh={(b) => setBatch(b)}
            onSubmitted={() => router.push("/employer/jobs/imports/list")}
            onStartOver={() => { setBatch(null); setMode("picker"); setError(null); }}
          />
        )}
      </div>
    </main>
  );
}

function ModePicker({ onPick }: { onPick: (m: Mode) => void }) {
  const options: { mode: Mode; icon: typeof Link2; label: string; desc: string; hint: string }[] = [
    {
      mode: "url", icon: Link2, label: "Paste your careers URL",
      desc: "Best if you use Workday, Greenhouse, or Lever. We'll detect the platform and pull every open job.",
      hint: "Fastest — ~30 seconds",
    },
    {
      mode: "csv", icon: FileSpreadsheet, label: "Upload a CSV / spreadsheet",
      desc: "One row per job. We'll show you a template and parse it into the standard format.",
      hint: "Best if you don't use a supported ATS",
    },
    {
      mode: "manual", icon: Plus, label: "Enter jobs by hand",
      desc: "Add one or a few jobs at a time using a clean form.",
      hint: "Best for a single posting",
    },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {options.map((opt) => (
        <button
          key={opt.mode}
          onClick={() => onPick(opt.mode)}
          className="group flex flex-col items-start rounded-xl border border-hairline bg-white p-5 text-left shadow-[0_1px_2px_rgba(12,10,9,0.04)] transition-shadow hover:shadow-[0_8px_28px_-12px_rgba(12,10,9,0.12)]"
        >
          <opt.icon className="h-5 w-5 text-cohere-green" strokeWidth={1.75} />
          <h3 className="mt-3 font-display text-feature text-cohere-ink">{opt.label}</h3>
          <p className="mt-2 text-caption text-slate leading-relaxed">{opt.desc}</p>
          <span className="mono-label mt-4 text-studio-maroon">{opt.hint}</span>
          <span className="mt-3 inline-flex items-center gap-1 text-caption font-medium text-cohere-ink">
            Continue <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
          </span>
        </button>
      ))}
    </div>
  );
}

function UrlMode(props: { token: string; loading: boolean; setLoading: (b: boolean) => void;
  onError: (e: string | null) => void; onParsed: (b: BatchDetail) => void; onBack: () => void;
  onSwitchToCsv: () => void }) {
  const [url, setUrl] = useState("");
  const [unsupported, setUnsupported] = useState(false);
  async function go() {
    if (!url.trim() || props.loading) return;
    props.setLoading(true); props.onError(null); setUnsupported(false);
    try {
      const b = await importFromUrl(props.token, url.trim());
      props.onParsed(b);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not import";
      // Backend returns 400 with a "couldn't detect a supported career-page platform" message
      // when the ATS is unknown. Show a specific unsupported card.
      if (/couldn.?t detect|supported career|Workday, Greenhouse, Lever/i.test(msg)) {
        setUnsupported(true);
        props.onError(null);
      } else {
        props.onError(msg);
      }
    } finally {
      props.setLoading(false);
    }
  }
  return (
    <div className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
      <button onClick={props.onBack} className="mb-4 text-caption text-slate hover:text-cohere-ink">← Back</button>
      <h2 className="font-display text-feature text-cohere-ink">Paste your careers page URL</h2>
      <p className="mt-2 text-body text-slate">
        We support Workday, Greenhouse, and Lever today. We'll detect the platform automatically.
      </p>
      <div className="mt-4 flex gap-2">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") go(); }}
          placeholder="https://jobs.example.com/careers"
          className="input-cohere text-caption"
        />
        <button onClick={go} disabled={!url.trim() || props.loading} className="btn-primary shrink-0">
          {props.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
          Pull jobs
        </button>
      </div>
      <p className="mt-3 text-micro text-slate-muted">
        Examples that work today: any <code>*.myworkdayjobs.com</code>, <code>boards.greenhouse.io/&lt;company&gt;</code>, or <code>jobs.lever.co/&lt;company&gt;</code> URL.
      </p>
      {unsupported && (
        <div className="mt-4 rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-studio-maroon mt-0.5 shrink-0" />
            <div>
              <p className="text-body text-cohere-ink font-medium">
                We didn't recognize this ATS.
              </p>
              <p className="mt-1 text-caption text-slate">
                We currently support Workday, Greenhouse, and Lever URLs. Try our CSV template instead.
              </p>
              <button
                onClick={props.onSwitchToCsv}
                className="mt-3 inline-flex items-center gap-1 text-caption font-medium text-cohere-blue underline"
              >
                Use CSV template <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CsvMode(props: { token: string; loading: boolean; setLoading: (b: boolean) => void;
  onError: (e: string | null) => void; onParsed: (b: BatchDetail) => void; onBack: () => void }) {
  const [csv, setCsv] = useState("");
  async function go() {
    if (!csv.trim() || props.loading) return;
    props.setLoading(true); props.onError(null);
    try {
      const b = await importFromCsv(props.token, csv.trim());
      props.onParsed(b);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not parse CSV";
      props.onError(msg);
    } finally {
      props.setLoading(false);
    }
  }
  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return;
    setCsv(await f.text());
  }
  return (
    <div className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
      <button onClick={props.onBack} className="mb-4 text-caption text-slate hover:text-cohere-ink">← Back</button>
      <h2 className="font-display text-feature text-cohere-ink">Upload a CSV of jobs</h2>
      <p className="mt-2 text-body text-slate">
        At minimum we need a <code>title</code> column. Other supported columns: city, state, description, requirements, pay_min, pay_max, pay_type, experience_level, source_url.
      </p>
      <div className="mt-4 flex items-center gap-3">
        <button onClick={() => setCsv(CSV_TEMPLATE)} className="text-caption text-cohere-blue underline">
          Load sample
        </button>
        <label className="inline-flex cursor-pointer items-center gap-1.5 text-caption text-slate hover:text-cohere-ink">
          <FileSpreadsheet className="h-4 w-4" /> Upload .csv
          <input type="file" accept=".csv,.tsv,text/csv" onChange={onFile} className="hidden" />
        </label>
      </div>
      <textarea
        value={csv}
        onChange={(e) => setCsv(e.target.value)}
        rows={10}
        placeholder="title,city,state,description,requirements,pay_min,pay_max,pay_type"
        className="input-cohere mt-3 w-full resize-y text-caption"
      />
      <button onClick={go} disabled={!csv.trim() || props.loading} className="btn-primary mt-3 inline-flex items-center gap-2">
        {props.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
        Parse & preview
      </button>
    </div>
  );
}

function ManualMode(props: { token: string; loading: boolean; setLoading: (b: boolean) => void;
  onError: (e: string | null) => void; onParsed: (b: BatchDetail) => void; onBack: () => void }) {
  const [row, setRow] = useState<Partial<ImportRow>>({ country: "US" });
  function set<K extends keyof ImportRow>(k: K, v: ImportRow[K] | string) {
    setRow((r) => ({ ...r, [k]: v as never }));
  }
  async function go() {
    if (!row.title_raw?.trim() || props.loading) return;
    props.setLoading(true); props.onError(null);
    try {
      const b = await importManual(props.token, [row]);
      props.onParsed(b);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not save";
      props.onError(msg);
    } finally {
      props.setLoading(false);
    }
  }
  return (
    <div className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
      <button onClick={props.onBack} className="mb-4 text-caption text-slate hover:text-cohere-ink">← Back</button>
      <h2 className="font-display text-feature text-cohere-ink">Enter a job by hand</h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Job title *" required>
          <input className="input-cohere" value={row.title_raw ?? ""} onChange={(e) => set("title_raw", e.target.value)} placeholder="e.g. Industrial Electrician" />
        </Field>
        <Field label="Source URL">
          <input className="input-cohere text-caption" value={row.source_url ?? ""} onChange={(e) => set("source_url", e.target.value)} placeholder="https://…" />
        </Field>
        <Field label="City"><input className="input-cohere" value={row.city ?? ""} onChange={(e) => set("city", e.target.value)} /></Field>
        <Field label="State"><input className="input-cohere uppercase" maxLength={2} value={row.state ?? ""} onChange={(e) => set("state", e.target.value.toUpperCase())} /></Field>
        <Field label="Pay min ($)"><input className="input-cohere" type="number" value={row.pay_min ?? ""} onChange={(e) => set("pay_min", Number(e.target.value) || (undefined as never))} /></Field>
        <Field label="Pay max ($)"><input className="input-cohere" type="number" value={row.pay_max ?? ""} onChange={(e) => set("pay_max", Number(e.target.value) || (undefined as never))} /></Field>
        <Field label="Pay type">
          <select className="input-cohere" value={row.pay_type ?? ""} onChange={(e) => set("pay_type", e.target.value)}>
            <option value="">Select…</option><option value="hourly">Hourly</option><option value="annual">Annual</option>
          </select>
        </Field>
        <Field label="Experience">
          <select className="input-cohere" value={row.experience_level ?? ""} onChange={(e) => set("experience_level", e.target.value)}>
            <option value="">Select…</option><option value="entry">Entry</option><option value="mid">Mid</option><option value="senior">Senior</option>
          </select>
        </Field>
      </div>
      <div className="mt-4">
        <Field label="Description">
          <textarea className="input-cohere min-h-[120px] resize-y" value={row.description_raw ?? ""} onChange={(e) => set("description_raw", e.target.value)} placeholder="What the role does and what kind of trades worker it's looking for." />
        </Field>
      </div>
      <div className="mt-3 grid gap-4 sm:grid-cols-2">
        <Field label="Requirements">
          <textarea className="input-cohere min-h-[80px] resize-y" value={row.requirements_raw ?? ""} onChange={(e) => set("requirements_raw", e.target.value)} placeholder="Required certifications, experience…" />
        </Field>
        <Field label="Preferred / nice to have">
          <textarea className="input-cohere min-h-[80px] resize-y" value={row.preferred_qualifications_raw ?? ""} onChange={(e) => set("preferred_qualifications_raw", e.target.value)} />
        </Field>
      </div>
      <button onClick={go} disabled={!row.title_raw?.trim() || props.loading} className="btn-primary mt-4 inline-flex items-center gap-2">
        {props.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
        Save and preview
      </button>
    </div>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-caption font-medium text-slate">
        {label}{required && <span className="text-studio-maroon">*</span>}
      </span>
      {children}
    </label>
  );
}

function PreviewBatch({
  token, batch, onRefresh, onSubmitted, onStartOver,
}: {
  token: string; batch: BatchDetail;
  onRefresh: (b: BatchDetail) => void;
  onSubmitted: () => void;
  onStartOver: () => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const staged = batch.rows.filter((r) => r.status === "staged");

  async function submit() {
    setSubmitting(true); setErr(null);
    try {
      await submitBatch(token, batch.id, note || undefined);
      onSubmitted();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not submit";
      setErr(msg);
      setSubmitting(false);
    }
  }

  async function exclude(id: string) {
    await excludeRow(token, batch.id, id);
    const refreshed = { ...batch, rows: batch.rows.map((r) => r.id === id ? { ...r, status: "excluded" as const } : r) };
    onRefresh(refreshed);
  }

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-cohere-blue/20 bg-wash-blue p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h2 className="font-display text-feature text-cohere-ink">Preview before submit</h2>
            <p className="mt-1 text-body text-slate">
              <strong>{staged.length}</strong> job{staged.length === 1 ? "" : "s"} ready to send for SKILLED admin review.
              {batch.platform ? <> Detected platform: <span className="font-medium text-cohere-ink">{batch.platform}</span>.</> : null}
            </p>
          </div>
          <button onClick={onStartOver} className="text-caption text-slate hover:text-cohere-ink">Start over</button>
        </div>
      </div>

      {err && (
        <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4 text-body text-cohere-ink">{err}</div>
      )}

      <div className="overflow-hidden rounded-xl border border-hairline bg-white shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
        <table className="w-full text-body">
          <thead className="border-b border-hairline bg-stone/40">
            <tr>
              <th className="px-4 py-3 text-left text-caption font-medium text-slate">Title</th>
              <th className="px-4 py-3 text-left text-caption font-medium text-slate">Location</th>
              <th className="px-4 py-3 text-left text-caption font-medium text-slate">Pay</th>
              <th className="px-4 py-3 text-left text-caption font-medium text-slate">Experience</th>
              <th className="px-4 py-3 text-right text-caption font-medium text-slate">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {batch.rows.map((r) => (
              <RowItem
                key={r.id} row={r} batchId={batch.id} token={token}
                editing={editing === r.id}
                onStartEdit={() => setEditing(r.id)}
                onStopEdit={() => setEditing(null)}
                onExclude={() => exclude(r.id)}
                onSaved={(updated) => {
                  onRefresh({ ...batch, rows: batch.rows.map((x) => x.id === updated.id ? updated : x) });
                  setEditing(null);
                }}
              />
            ))}
          </tbody>
        </table>
      </div>

      <div className="rounded-xl border border-hairline bg-white p-5 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
        <MonoLabel className="mb-2 block">Optional note to admins</MonoLabel>
        <textarea
          value={note} onChange={(e) => setNote(e.target.value)}
          rows={2}
          placeholder="e.g. These postings expand our Carrollton plant team. Targeting electricians and welders."
          className="input-cohere min-h-[64px] resize-y"
        />
        <div className="mt-4 flex items-center justify-between">
          <p className="text-caption text-slate-muted">
            Submitting will notify SKILLED admins. You'll get an email when they review.
          </p>
          <button onClick={submit} disabled={submitting || staged.length === 0} className="btn-primary inline-flex items-center gap-2">
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Submit {staged.length} job{staged.length === 1 ? "" : "s"} for review
          </button>
        </div>
      </div>
    </div>
  );
}

function RowItem({
  row, batchId, token, editing, onStartEdit, onStopEdit, onExclude, onSaved,
}: {
  row: ImportRow; batchId: string; token: string; editing: boolean;
  onStartEdit: () => void; onStopEdit: () => void; onExclude: () => void;
  onSaved: (r: ImportRow) => void;
}) {
  const [draft, setDraft] = useState<ImportRow>(row);
  const isDropped = row.status === "excluded";
  const titleInvalid = !draft.title_raw?.trim();
  async function save() {
    if (titleInvalid) return;
    await editRow(token, batchId, row.id, draft);
    onSaved(draft);
  }
  if (editing) {
    return (
      <tr className="bg-stone/40">
        <td colSpan={5} className="p-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <input
                className="input-cohere w-full"
                value={draft.title_raw}
                onChange={(e) => setDraft({ ...draft, title_raw: e.target.value })}
                placeholder="Title"
                aria-invalid={titleInvalid ? "true" : "false"}
              />
              {titleInvalid && (
                <p className="mt-1 text-micro text-studio-maroon" role="alert">Required</p>
              )}
            </div>
            <input className="input-cohere" value={draft.city ?? ""} onChange={(e) => setDraft({ ...draft, city: e.target.value })} placeholder="City" />
            <input className="input-cohere uppercase" maxLength={2} value={draft.state ?? ""} onChange={(e) => setDraft({ ...draft, state: e.target.value.toUpperCase() })} placeholder="State" />
            <input className="input-cohere" value={draft.pay_raw ?? ""} onChange={(e) => setDraft({ ...draft, pay_raw: e.target.value })} placeholder="Pay ($24–$28/hr)" />
          </div>
          <div className="mt-3">
            <textarea className="input-cohere min-h-[100px] resize-y" value={draft.description_raw ?? ""} onChange={(e) => setDraft({ ...draft, description_raw: e.target.value })} placeholder="Description" />
          </div>
          <div className="mt-3 flex gap-2">
            <button
              onClick={save}
              disabled={titleInvalid}
              className="btn-primary text-caption disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Save
            </button>
            <button onClick={onStopEdit} className="btn-pill-outline text-caption">Cancel</button>
          </div>
        </td>
      </tr>
    );
  }
  return (
    <tr className={isDropped ? "opacity-50" : ""}>
      <td className="px-4 py-3 align-top">
        <div className="font-medium text-cohere-ink">{row.title_raw}</div>
        {row.source_url && <div className="mt-0.5 text-micro text-slate-muted truncate max-w-[280px]">{row.source_url}</div>}
      </td>
      <td className="px-4 py-3 align-top text-caption text-slate">
        {[row.city, row.state].filter(Boolean).join(", ") || "—"}
      </td>
      <td className="px-4 py-3 align-top text-caption text-slate">
        {row.pay_raw || (row.pay_min ? `$${row.pay_min}${row.pay_max ? `–$${row.pay_max}` : ""}${row.pay_type ? `/${row.pay_type === "hourly" ? "hr" : "yr"}` : ""}` : "—")}
      </td>
      <td className="px-4 py-3 align-top text-caption text-slate">{row.experience_level || "—"}</td>
      <td className="px-4 py-3 align-top text-right">
        {isDropped ? (
          <span className="text-caption text-slate-muted">Excluded</span>
        ) : (
          <div className="flex justify-end gap-1.5">
            <button onClick={onStartEdit} aria-label="Edit"
              className="rounded-md border border-hairline p-1.5 text-slate-muted hover:border-cohere-ink hover:text-cohere-ink">
              <Edit3 className="h-3.5 w-3.5" />
            </button>
            <button onClick={onExclude} aria-label="Exclude"
              className="rounded-md border border-hairline p-1.5 text-slate-muted hover:border-studio-maroon hover:text-studio-maroon">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </td>
    </tr>
  );
}
