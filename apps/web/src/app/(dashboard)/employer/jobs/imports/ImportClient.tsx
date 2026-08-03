"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Link2, FileSpreadsheet, FileText, Plus, Loader2, ArrowRight,
  CheckCircle2, AlertTriangle, Edit3, X, Send, Eye, RefreshCw, Trash2,
} from "lucide-react";

import {
  BatchDetail, ImportRow,
  getBatch, importFromCsv, importManual, submitBatch, editRow, excludeRow, restoreRow,
} from "@/lib/api/jobImports";
import {
  CareerSource, CareerSourcePull, CareerSourcePullHistoryItem,
  careerSourcePullHistory, deleteCareerSource, listCareerSources,
  pullCareerSource, saveCareerSource, updateCareerSourceSettings,
} from "@/lib/api/careerSource";
import { SyncTimeline, relativeTime } from "@/components/careersync/SyncTimeline";
import { PageHeader, MonoLabel, ErrorDetails } from "@/components/ui";

type Mode = "picker" | "url" | "csv" | "manual" | "preview";

const CSV_TEMPLATE = `title,city,state,description,requirements,pay_min,pay_max,pay_type,experience_level,source_url
Welder I,Carrollton,GA,"Work in our facility welding steel components.","High-school diploma; 1+ year welding.",22,28,hourly,entry,https://example.com/welder-i
Industrial Electrician,Atlanta,GA,"Maintain and repair electrical systems in a manufacturing plant.","Journeyman electrician license; 3+ years in industrial settings.",35,42,hourly,mid,https://example.com/electrician`;

/** Human sentence for an error — a server-humanized string or an ApiError. */
function errText(e: unknown, fallback: string): string {
  if (typeof e === "string" && e.trim()) return e;
  return e instanceof Error && e.message ? e.message : fallback;
}

export function ImportClient({ token }: { token: string }) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("picker");
  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  // Errors belong to the mode card they happened in — switching modes (or
  // going back) always starts clean.
  const switchMode = useCallback((m: Mode) => {
    setError(null);
    setMode(m);
  }, []);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Post jobs"
          title="Import jobs"
          lead="You'll preview every row before it goes to SKILLED admins for approval."
          actions={
            <Link href="/employer/jobs/imports/list" className="btn-pill-outline inline-flex items-center gap-1">
              <Eye className="h-4 w-4" /> My batches
            </Link>
          }
        />

        {/* The page reads top-to-bottom: what do you want to do → your
            existing setup → history (collapsed inside the setup section). */}
        {mode === "picker" && !batch && (
          <>
            <section>
              <h2 className="font-display text-feature text-cohere-ink">How do you want to add jobs?</h2>
              <p className="mt-1 text-caption text-slate">
                Everything here goes through SKILLED review before publishing. Need one job live
                right now?{" "}
                <Link href="/employer/jobs/new" className="text-cohere-blue underline">
                  Post a job
                </Link>. It publishes instantly.
              </p>
              <div className="mt-4">
                <ModePicker onPick={switchMode} />
              </div>
            </section>
            <CareersSourceSection token={token} onAddAnother={() => switchMode("url")} />
          </>
        )}

        {mode === "url" && !batch && (
          <UrlMode token={token} loading={loading} setLoading={setLoading}
            error={error} onError={setError}
            onParsed={(b) => { setBatch(b); setError(null); setMode("preview"); }}
            onBack={() => switchMode("picker")}
            onSwitchToCsv={() => switchMode("csv")} />
        )}

        {mode === "csv" && !batch && (
          <CsvMode token={token} loading={loading} setLoading={setLoading}
            error={error} onError={setError}
            onParsed={(b) => { setBatch(b); setError(null); setMode("preview"); }}
            onBack={() => switchMode("picker")} />
        )}

        {mode === "manual" && !batch && (
          <ManualMode token={token} loading={loading} setLoading={setLoading}
            error={error} onError={setError}
            onParsed={(b) => { setBatch(b); setError(null); setMode("preview"); }}
            onBack={() => switchMode("picker")} />
        )}

        {batch && (
          <PreviewBatch
            token={token} batch={batch}
            onRefresh={(b) => setBatch(b)}
            onSubmitted={(submittedCount) =>
              router.push(`/employer/jobs/imports/list?submitted=${batch.id}&count=${submittedCount}`)}
            onStartOver={() => { setBatch(null); switchMode("picker"); }}
          />
        )}
      </div>
    </main>
  );
}

/** Inline error line rendered INSIDE the active mode card, under its input. */
function InlineError({ error }: { error: unknown }) {
  if (error == null) return null;
  return (
    <div className="mt-3 rounded-[10px] border border-studio-maroon/30 bg-studio-maroon/[0.06] p-3" role="alert">
      <p className="text-caption text-cohere-ink">
        <AlertTriangle className="mr-1.5 inline h-4 w-4 text-studio-maroon" />
        {errText(error, "Something went wrong. Try again.")}
      </p>
      <ErrorDetails error={error} />
    </div>
  );
}

function pullSummary(p: CareerSourcePull): string {
  const secs = p.duration_ms != null ? ` in ${(p.duration_ms / 1000).toFixed(1)}s` : "";
  if (p.sync_mode === "not_modified") {
    return `checked your site${secs}, nothing changed, ${p.jobs_found} job${p.jobs_found === 1 ? "" : "s"} still live`;
  }
  const parts = [
    `found ${p.jobs_found} on the site${secs}`,
    `${p.jobs_new} new`,
    `${p.jobs_updated} updated`,
    `${p.jobs_removed} removed`,
  ];
  if (p.jobs_rejected > 0) parts.push(`${p.jobs_rejected} not trades roles`);
  if (p.links_broken > 0) parts.push(`${p.links_broken} broken link${p.links_broken === 1 ? "" : "s"}`);
  if (p.sync_mode === "relearned") parts.push("site structure changed, so we relearned the page layout");
  return parts.join(" · ");
}

const INTERVAL_OPTIONS = [
  { hours: 1, label: "every hour" },
  { hours: 3, label: "every 3 hours" },
  { hours: 6, label: "every 6 hours" },
  { hours: 12, label: "every 12 hours" },
  { hours: 24, label: "once a day" },
];

/** A source that has been pulled but never produced a single job. */
function neverConnected(s: CareerSource): boolean {
  return !!s.last_pulled_at && s.last_status !== "ok" && s.jobs_found === 0;
}

function CareersSourceSection({
  token,
  onAddAnother,
}: {
  token: string;
  /** Adding a URL happens in the "Paste your careers URL" method card — one entrance. */
  onAddAnother: () => void;
}) {
  const [sources, setSources] = useState<CareerSource[] | null>(null);
  const [history, setHistory] = useState<CareerSourcePullHistoryItem[]>([]);
  const [pulling, setPulling] = useState<string | null>(null); // source id in flight
  const [lastPull, setLastPull] = useState<CareerSourcePull | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [confirmingRemove, setConfirmingRemove] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([
        listCareerSources(token),
        careerSourcePullHistory(token),
      ]);
      setSources(s);
      setHistory(h);
    } catch {
      setSources([]);
    }
  }, [token]);

  useEffect(() => { refresh(); }, [refresh]);

  async function runPull(sourceId: string) {
    if (pulling) return;
    setPulling(sourceId); setError(null); setLastPull(null);
    try {
      const result = await pullCareerSource(token, sourceId);
      setLastPull(result);
      if (result.status !== "ok") {
        setError(result.error || "The pull failed. Check the URL and try again.");
      }
      await refresh();
    } catch (e: unknown) {
      setError(e);
    } finally {
      setPulling(null);
    }
  }

  async function remove(sourceId: string) {
    try {
      await deleteCareerSource(token, sourceId);
      setLastPull(null);
      setConfirmingRemove(null);
      await refresh();
    } catch (e: unknown) {
      setError(e);
    }
  }

  async function saveSettings(
    sourceId: string,
    settings: { auto_sync_enabled?: boolean; auto_sync_interval_hours?: number },
  ) {
    try {
      const updated = await updateCareerSourceSettings(token, sourceId, settings);
      setSources((prev) => (prev ?? []).map((s) => (s.id === sourceId ? updated : s)));
    } catch (e: unknown) {
      setError(e);
    }
  }

  // While loading or with nothing connected, the section stays out of the way —
  // the "Paste your careers URL" method card above is the single entrance.
  if (sources === null || sources.length === 0) return null;

  return (
    <section className="pt-2">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-display text-feature text-cohere-ink">
          Your connected careers {sources.length === 1 ? "page" : "pages"}
        </h2>
        <button
          onClick={onAddAnother}
          className="text-body text-slate transition-colors hover:text-cohere-ink"
        >
          Add another page →
        </button>
      </div>
      <p className="mt-1 text-caption text-slate">
        We keep pulling skilled-trades roles from these pages and hold anything with a broken
        apply link for review.
      </p>

      <div className="mt-4 rounded-[10px] border border-hairline bg-white">
      {sources.map((s) => {
        const failed = neverConnected(s);
        return (
        <div
          key={s.id}
          className={`border-t border-hairline px-5 py-3.5 first:border-t-0 ${failed ? "border-l-2 border-l-studio-maroon bg-studio-maroon/[0.03]" : ""}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-body font-medium text-cohere-ink">{s.url}</p>
              {failed ? (
                <>
                  <p className="mt-0.5 text-caption text-studio-maroon">
                    <AlertTriangle className="mr-1 inline h-3.5 w-3.5" />
                    We couldn&rsquo;t connect to this page
                    {s.last_error ? `: ${s.last_error}` : "."}
                  </p>
                  <p className="mt-1 text-caption text-slate">
                    Automatic syncing stays off until a pull finds at least one job.{" "}
                    <button
                      onClick={() => setConfirmingRemove(s.id)}
                      className="text-studio-maroon underline"
                    >
                      Remove
                    </button>
                    {" or "}
                    <button onClick={onAddAnother} className="text-cohere-blue underline">
                      try another page
                    </button>
                    .
                  </p>
                </>
              ) : (
                <>
                  <p className="mt-0.5 text-caption text-slate">
                    {s.platform ? `Detected platform: ${s.platform}. ` : ""}
                    {s.last_pulled_at
                      ? `Last synced ${relativeTime(s.last_pulled_at)} · ${s.jobs_found} job${s.jobs_found === 1 ? "" : "s"} on the site.`
                      : "Not pulled yet."}
                    {s.has_profile ? " We've learned this page's layout, so refreshes are instant." : ""}
                    {s.last_status === "error" && s.last_error ? ` Last sync failed: ${s.last_error}` : ""}
                  </p>
                  <p className="mt-1 text-caption text-slate">
                    {s.auto_sync_enabled ? (
                      <>
                        Auto-syncs{" "}
                        <select
                          value={s.auto_sync_interval_hours}
                          onChange={(e) =>
                            saveSettings(s.id, { auto_sync_interval_hours: Number(e.target.value) })}
                          className="rounded-[8px] border border-hairline bg-white px-1.5 py-0.5 text-caption text-cohere-ink"
                          aria-label="Auto-sync frequency"
                        >
                          {INTERVAL_OPTIONS.map((o) => (
                            <option key={o.hours} value={o.hours}>{o.label}</option>
                          ))}
                          {!INTERVAL_OPTIONS.some((o) => o.hours === s.auto_sync_interval_hours) && (
                            <option value={s.auto_sync_interval_hours}>
                              every {s.auto_sync_interval_hours} hours
                            </option>
                          )}
                        </select>
                        {s.next_auto_sync_at &&
                          ` · next around ${new Date(s.next_auto_sync_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`}
                        {" · "}
                        <button
                          onClick={() => saveSettings(s.id, { auto_sync_enabled: false })}
                          className="text-slate underline hover:text-cohere-ink"
                        >
                          Turn off
                        </button>
                      </>
                    ) : (
                      <>
                        Auto-sync is off ·{" "}
                        <button
                          onClick={() => saveSettings(s.id, { auto_sync_enabled: true })}
                          className="text-slate underline hover:text-cohere-ink"
                        >
                          Turn on
                        </button>
                      </>
                    )}
                  </p>
                </>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {s.batch_id && !failed && (
                <Link
                  href={`/employer/jobs/imports/${s.batch_id}`}
                  className="btn-pill-outline inline-flex items-center gap-1.5 text-caption"
                >
                  <Eye className="h-4 w-4" /> Review jobs
                </Link>
              )}
              <button
                onClick={() => runPull(s.id)}
                disabled={pulling !== null}
                className={`inline-flex items-center gap-1.5 text-caption ${failed ? "btn-pill-outline" : "btn-primary"}`}
              >
                {pulling === s.id
                  ? <Loader2 className="h-4 w-4 animate-spin" />
                  : <RefreshCw className="h-4 w-4" />}
                {failed ? "Try again" : s.last_pulled_at ? "Refresh from site" : "Pull jobs"}
              </button>
              <button
                onClick={() => setConfirmingRemove(s.id)}
                aria-label="Remove this careers page"
                className="rounded-full border border-hairline p-2 text-slate-muted hover:border-studio-maroon hover:text-studio-maroon"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Inline confirm — same pattern as the application-detail knockout guard. */}
          {confirmingRemove === s.id && (
            <div className="mt-3 flex flex-wrap items-center gap-3 rounded-[10px] border border-studio-maroon/30 bg-studio-maroon/[0.06] px-4 py-2.5">
              <p className="text-caption text-cohere-ink">
                Remove this careers page? Its synced batch stays, but we&rsquo;ll stop pulling from it.
              </p>
              <div className="flex gap-2">
                <button onClick={() => remove(s.id)} className="btn-primary text-caption">
                  Remove page
                </button>
                <button onClick={() => setConfirmingRemove(null)} className="btn-pill-outline text-caption">
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
        );
      })}

      {lastPull && lastPull.status === "ok" && (
        <div className="border-t border-hairline px-5 py-3.5">
          <p className="text-body text-cohere-ink">
            <CheckCircle2 className="mr-1.5 inline h-4 w-4 text-cohere-green" />
            Pull complete: {pullSummary(lastPull)}.
            {lastPull.batch_id && (
              <>
                {" "}
                <Link href={`/employer/jobs/imports/${lastPull.batch_id}`} className="font-medium text-cohere-blue underline">
                  Review and submit for approval
                </Link>
              </>
            )}
          </p>
          {lastPull.links_broken > 0 && (
            <p className="mt-1 text-caption text-slate">
              Jobs with broken apply links stay held for review. They never publish silently.
            </p>
          )}
        </div>
      )}

      {error != null && (
        <div className="border-t border-hairline px-5 py-3.5">
          <p className="text-caption text-cohere-ink">
            <AlertTriangle className="mr-1.5 inline h-4 w-4 text-studio-maroon" />
            {errText(error, "Something went wrong. Try again.")}
          </p>
          <ErrorDetails error={error} />
        </div>
      )}

      {/* History stays collapsed by default — one quiet toggle, no timeline wall. */}
      {history.length > 0 && (
        <div className="border-t border-hairline">
          <div className="flex items-baseline justify-between px-5 py-3.5">
            <h3 className="text-body font-medium text-cohere-ink">Sync activity</h3>
            <button
              onClick={() => setShowHistory((v) => !v)}
              aria-expanded={showHistory}
              className="text-caption text-slate hover:text-cohere-ink"
            >
              {showHistory ? "Hide activity" : `Show activity (${history.length})`}
            </button>
          </div>
          {showHistory && <SyncTimeline pulls={history} />}
        </div>
      )}
      </div>
    </section>
  );
}

function ModePicker({ onPick }: { onPick: (m: Mode) => void }) {
  const options: { mode: Mode; icon: typeof Link2; label: string; desc: string; hint: string; publish: string }[] = [
    {
      mode: "url", icon: Link2, label: "Paste your careers URL",
      desc: "Connect your careers page once. We pull every open trades role and can keep it synced.",
      hint: "Fastest, about 30 seconds",
      publish: "Pulled jobs go to SKILLED review before publishing.",
    },
    {
      mode: "csv", icon: FileSpreadsheet, label: "Upload a CSV / spreadsheet",
      desc: "One row per job. We'll show you a template and parse it into the standard format.",
      hint: "Best for spreadsheets or exports from any system",
      publish: "Rows go to SKILLED review before publishing.",
    },
    {
      mode: "manual", icon: Plus, label: "Enter jobs by hand",
      desc: "Add one or a few jobs at a time using a clean form.",
      hint: "Best for a handful of postings",
      publish: "Entered jobs go to SKILLED review before publishing.",
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
          <h3 className="mt-3 text-[1.0625rem] font-medium text-cohere-ink">{opt.label}</h3>
          <p className="mt-2 text-caption text-slate leading-relaxed">{opt.desc}</p>
          <span className="mono-label mt-4 text-studio-maroon">{opt.hint}</span>
          <span className="mt-2 text-micro text-slate-muted">{opt.publish}</span>
          <span className="mt-3 inline-flex items-center gap-1 text-caption font-medium text-cohere-ink">
            Continue <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
          </span>
        </button>
      ))}
    </div>
  );
}

/**
 * The ONE entrance for careers-page URLs. Connecting a URL saves it as a
 * career source, runs the first pull, and opens the resulting batch preview —
 * already-connected pages are listed here so nobody adds the same URL twice.
 */
function UrlMode(props: { token: string; loading: boolean; setLoading: (b: boolean) => void;
  error: unknown; onError: (e: unknown) => void;
  onParsed: (b: BatchDetail) => void; onBack: () => void;
  onSwitchToCsv: () => void }) {
  const [url, setUrl] = useState("");
  const [showCsvOnramp, setShowCsvOnramp] = useState(false);
  const [sources, setSources] = useState<CareerSource[] | null>(null);

  useEffect(() => {
    listCareerSources(props.token).then(setSources).catch(() => setSources([]));
  }, [props.token]);

  async function openPull(pull: CareerSourcePull) {
    // The CSV rescue onramp keys off the ACTUAL pull statuses — no string
    // matching. Any non-ok outcome offers the template as the way out.
    if (pull.status === "no_jobs" || pull.status === "error" || pull.status === "blocked") {
      props.onError(pull.error || "We couldn't pull jobs from that page.");
      setShowCsvOnramp(true);
      return;
    }
    if (pull.batch_id) {
      const b = await getBatch(props.token, pull.batch_id);
      props.onParsed(b);
    }
  }

  async function connectAndPull() {
    if (!url.trim() || props.loading) return;
    props.setLoading(true); props.onError(null); setShowCsvOnramp(false);
    try {
      const saved = await saveCareerSource(props.token, url.trim());
      const pull = await pullCareerSource(props.token, saved.id);
      await openPull(pull);
    } catch (e: unknown) {
      props.onError(e);
    } finally {
      props.setLoading(false);
    }
  }

  async function refreshSource(sourceId: string) {
    if (props.loading) return;
    props.setLoading(true); props.onError(null); setShowCsvOnramp(false);
    try {
      const pull = await pullCareerSource(props.token, sourceId);
      await openPull(pull);
    } catch (e: unknown) {
      props.onError(e);
    } finally {
      props.setLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
      <button onClick={props.onBack} className="mb-4 text-caption text-slate hover:text-cohere-ink">← Back</button>
      <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Connect your careers page</h2>
      <p className="mt-2 text-body text-slate">
        Paste the page once. We detect the platform, pull every open trades role, and keep the
        connection so you can refresh from your site any time.
      </p>

      {sources !== null && sources.length > 0 && (
        <div className="mt-4 rounded-[10px] border border-hairline">
          <p className="px-4 py-2.5 text-caption font-medium text-cohere-ink">
            Already connected. Refresh instead of adding the same page again
          </p>
          <div className="divide-y divide-hairline border-t border-hairline">
            {sources.map((s) => (
              <div key={s.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-caption text-cohere-ink">{s.url}</p>
                  <p className="text-micro text-slate-muted">
                    {s.last_pulled_at ? `Last synced ${relativeTime(s.last_pulled_at)} · ${s.jobs_found} job${s.jobs_found === 1 ? "" : "s"}` : "Not pulled yet"}
                  </p>
                </div>
                <button
                  onClick={() => refreshSource(s.id)}
                  disabled={props.loading}
                  className="btn-pill-outline inline-flex shrink-0 items-center gap-1.5 text-caption"
                >
                  <RefreshCw className="h-3.5 w-3.5" /> Refresh from site
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 flex gap-2">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") connectAndPull(); }}
          placeholder={sources && sources.length > 0
            ? "Add another careers page URL"
            : "https://careers.yourcompany.com or your Workday / Greenhouse / Lever board"}
          className="input-cohere text-caption"
          aria-label="Careers page URL"
        />
        <button onClick={connectAndPull} disabled={!url.trim() || props.loading} className="btn-primary shrink-0 inline-flex items-center gap-1.5">
          {props.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
          Connect and pull
        </button>
      </div>
      <InlineError error={props.error} />
      <p className="mt-3 text-micro text-slate-muted">
        Works with Workday, Greenhouse, and Lever boards, plus most careers pages that list jobs
        with links or schema.org markup, e.g. any <code>*.myworkdayjobs.com</code>,{" "}
        <code>boards.greenhouse.io/&lt;company&gt;</code>, or <code>jobs.lever.co/&lt;company&gt;</code> URL.
      </p>
      {showCsvOnramp && (
        <div className="mt-4 rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-studio-maroon mt-0.5 shrink-0" />
            <div>
              <p className="text-body text-cohere-ink font-medium">
                We didn&rsquo;t recognize this careers page.
              </p>
              <p className="mt-1 text-caption text-slate">
                We couldn&rsquo;t pull job listings from that URL. If your jobs live on a
                different page, try that one, or use the CSV template instead.
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

/* ---------------------------------------------------------------------------
 * CSV contract + column mapping.
 *
 * The backend (apps/api/app/skilled_pro/job_imports.py) requires only `title`
 * and fuzzy-matches header aliases. We publish that contract honestly here,
 * and let users with ANY headers re-map columns before submit — the header
 * row is rewritten to canonical names client-side, so the payload shape
 * (csv_text) is unchanged.
 * ------------------------------------------------------------------------ */

const CSV_CONTRACT: { key: string; required?: boolean; desc: string; format: string }[] = [
  { key: "title", required: true, desc: "Job title (the only required column)", format: "Industrial Electrician" },
  { key: "city", desc: "City of the job site", format: "Carrollton" },
  { key: "state", desc: "Two-letter state code", format: "GA" },
  { key: "description", desc: "What the role does", format: "Maintain and repair electrical systems…" },
  { key: "requirements", desc: "Required certifications and experience", format: "Journeyman license; 3+ years" },
  { key: "pay_min", desc: "Minimum pay as a number, no $ or commas needed", format: "22" },
  { key: "pay_max", desc: "Maximum pay as a number", format: "28" },
  { key: "pay_type", desc: "How pay_min / pay_max are stated", format: "hourly or annual" },
  { key: "experience_level", desc: "Level the role is aimed at", format: "entry, mid, or senior" },
  { key: "source_url", desc: "The apply link on your site", format: "https://yoursite.com/jobs/123" },
];

/** Mapping targets — mirrors the backend's accepted columns + alias spellings. */
const MAP_TARGETS: { value: string; label: string; aliases: string[] }[] = [
  { value: "title", label: "title (required)", aliases: ["title", "job_title", "role", "position", "title_raw"] },
  { value: "description", label: "description", aliases: ["description", "summary", "about", "overview", "description_raw"] },
  { value: "responsibilities", label: "responsibilities", aliases: ["responsibilities", "duties", "what_youll_do", "responsibilities_raw"] },
  { value: "requirements", label: "requirements", aliases: ["requirements", "qualifications_required", "required", "requirements_raw"] },
  { value: "preferred", label: "preferred / nice to have", aliases: ["preferred", "preferred_qualifications", "nice_to_have", "preferred_qualifications_raw"] },
  { value: "city", label: "city", aliases: ["city"] },
  { value: "state", label: "state", aliases: ["state", "state_code", "region"] },
  { value: "country", label: "country", aliases: ["country"] },
  { value: "work_setting", label: "work_setting", aliases: ["work_setting", "remote", "on_site", "remote_setting"] },
  { value: "travel", label: "travel", aliases: ["travel", "travel_requirement"] },
  { value: "pay_min", label: "pay_min", aliases: ["pay_min", "min_pay", "salary_min", "min_salary"] },
  { value: "pay_max", label: "pay_max", aliases: ["pay_max", "max_pay", "salary_max", "max_salary"] },
  { value: "pay_type", label: "pay_type (hourly | annual)", aliases: ["pay_type", "salary_type"] },
  { value: "pay", label: "pay (free text, e.g. $24–$28/hr)", aliases: ["pay", "salary", "compensation", "pay_raw"] },
  { value: "experience_level", label: "experience_level (entry | mid | senior)", aliases: ["experience_level", "experience", "level", "seniority"] },
  { value: "posted_date", label: "posted_date", aliases: ["posted_date", "posted", "date"] },
  { value: "employment_type", label: "employment_type", aliases: ["employment_type", "type", "schedule"] },
  { value: "req_id", label: "req_id / requisition id", aliases: ["req_id", "requisition_id", "job_id", "id"] },
  { value: "source_url", label: "source_url (apply link)", aliases: ["source_url", "url", "link", "job_url"] },
  { value: "category", label: "category / department", aliases: ["category", "department", "team", "function"] },
];

function normalizeHeader(h: string): string {
  return h.trim().toLowerCase().replace(/[\s-]+/g, "_");
}

/** Quote-aware split of ONE csv line. */
function parseCsvLine(line: string, delim: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++; } else inQuotes = false;
      } else cur += ch;
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === delim) {
      out.push(cur); cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out;
}

/** Same delimiter candidates as the backend's csv.Sniffer call. */
function detectDelimiter(headerLine: string): string {
  let best = ",";
  let bestCount = 0;
  for (const d of [",", "\t", ";", "|"]) {
    const n = parseCsvLine(headerLine, d).length;
    if (n > bestCount) { best = d; bestCount = n; }
  }
  return best;
}

/** Auto-map a header to a canonical column — exact alias first, then loose. */
function autoMapHeader(header: string): string {
  const norm = normalizeHeader(header);
  const exact = MAP_TARGETS.find((t) => t.aliases.includes(norm));
  if (exact) return exact.value;
  const loose = MAP_TARGETS.find((t) =>
    t.aliases.some((a) => a.length >= 4 && norm.includes(a)),
  );
  return loose?.value ?? "";
}

function CsvMode(props: { token: string; loading: boolean; setLoading: (b: boolean) => void;
  error: unknown; onError: (e: unknown) => void;
  onParsed: (b: BatchDetail) => void; onBack: () => void }) {
  const [csv, setCsv] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  // Column index → canonical target ("" = ignore this column).
  const [mapping, setMapping] = useState<Record<number, string>>({});

  const parsed = useMemo(() => {
    const text = csv.trim();
    if (!text) return null;
    const lines = text.split(/\r?\n/);
    const delim = detectDelimiter(lines[0]);
    const headers = parseCsvLine(lines[0], delim).map((h) => h.trim());
    const dataLines = lines.slice(1).filter((l) => l.trim()).length;
    return { delim, headers, dataLines };
  }, [csv]);

  const headerKey = parsed ? parsed.headers.join(" ") : "";
  // Re-run auto-mapping whenever the header row changes.
  useEffect(() => {
    if (!parsed) { setMapping({}); return; }
    const next: Record<number, string> = {};
    const used = new Set<string>();
    parsed.headers.forEach((h, i) => {
      const target = autoMapHeader(h);
      if (target && !used.has(target)) {
        next[i] = target;
        used.add(target);
      } else {
        next[i] = "";
      }
    });
    setMapping(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headerKey]);

  const mappedValues = Object.values(mapping);
  const titleMapped = mappedValues.includes("title");

  function buildCsvText(): string {
    const text = csv.trim();
    if (!parsed) return text;
    const lines = text.split(/\r?\n/);
    // Rewrite the header row to canonical names; unmapped columns get a
    // header the backend won't match, so their cells are ignored.
    const canonical = parsed.headers.map((_, i) => mapping[i] || `ignored_${i + 1}`);
    return [canonical.join(parsed.delim), ...lines.slice(1)].join("\n");
  }

  async function go() {
    if (!csv.trim() || !titleMapped || props.loading) return;
    props.setLoading(true); props.onError(null);
    try {
      const b = await importFromCsv(props.token, buildCsvText(), fileName ?? undefined);
      props.onParsed(b);
    } catch (e: unknown) {
      props.onError(e);
    } finally {
      props.setLoading(false);
    }
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return;
    setFileName(f.name);
    setCsv(await f.text());
  }

  return (
    <div className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
      <button onClick={props.onBack} className="mb-4 text-caption text-slate hover:text-cohere-ink">← Back</button>
      <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Upload a CSV of jobs</h2>
      <p className="mt-2 text-body text-slate">
        One row per job. Only <code>title</code> is required. Every other column improves matching.
        Your headers don&rsquo;t have to match ours: you&rsquo;ll map columns before anything is imported.
      </p>

      {/* The contract — required vs recommended columns, formats, examples */}
      <div className="mt-4 overflow-x-auto rounded-[10px] border border-hairline">
        <table className="w-full min-w-[560px] text-caption">
          <thead>
            <tr className="border-b border-hairline text-left text-slate-muted">
              <th className="px-4 py-2 font-medium">Column</th>
              <th className="px-4 py-2 font-medium">Needed?</th>
              <th className="px-4 py-2 font-medium">What it is</th>
              <th className="px-4 py-2 font-medium">Format / example</th>
            </tr>
          </thead>
          <tbody>
            {CSV_CONTRACT.map((c) => (
              <tr key={c.key} className="border-t border-hairline first:border-t-0">
                <td className="px-4 py-2 font-medium text-cohere-ink"><code>{c.key}</code></td>
                <td className="px-4 py-2">
                  {c.required
                    ? <span className="font-medium text-studio-maroon">Required</span>
                    : <span className="text-slate-muted">Recommended</span>}
                </td>
                <td className="px-4 py-2 text-slate">{c.desc}</td>
                <td className="px-4 py-2 text-slate-muted">{c.format}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-micro text-slate-muted">
        Also accepted: responsibilities, preferred, country, work_setting, travel, pay (free text),
        posted_date, employment_type, req_id, category. Header names match case-insensitively and
        common variants (&ldquo;Job Title&rdquo;, &ldquo;salary_min&rdquo;) map automatically.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-4">
        <a
          href="/job-import-template.csv"
          download
          className="inline-flex items-center gap-1.5 text-caption font-medium text-cohere-blue underline"
        >
          <FileSpreadsheet className="h-4 w-4" /> Download template CSV
        </a>
        <label className="inline-flex cursor-pointer items-center gap-1.5 text-caption text-slate hover:text-cohere-ink">
          <FileText className="h-4 w-4" /> Upload .csv
          <input type="file" accept=".csv,.tsv,text/csv" onChange={onFile} className="hidden" />
        </label>
        <button onClick={() => { setFileName(null); setCsv(CSV_TEMPLATE); }} className="text-caption text-slate underline hover:text-cohere-ink">
          Load sample data
        </button>
      </div>

      <textarea
        value={csv}
        onChange={(e) => { setFileName(null); setCsv(e.target.value); }}
        rows={8}
        placeholder="Paste CSV here. First line must be the header row, e.g. title,city,state,pay_min,pay_max"
        className="input-cohere mt-3 w-full resize-y text-caption"
        aria-label="CSV contents"
      />

      {/* Column mapping — detected headers → our columns */}
      {parsed && parsed.headers.length > 0 && (
        <div className="mt-4 rounded-[10px] border border-hairline">
          <div className="border-b border-hairline px-4 py-2.5">
            <p className="text-caption font-medium text-cohere-ink">
              Map your columns
            </p>
            <p className="mt-0.5 text-micro text-slate-muted">
              {parsed.headers.length} column{parsed.headers.length === 1 ? "" : "s"} and{" "}
              {parsed.dataLines} data row{parsed.dataLines === 1 ? "" : "s"} detected
              {fileName ? ` in ${fileName}` : ""}. We matched what we could. Fix anything that&rsquo;s wrong.
            </p>
          </div>
          <div className="divide-y divide-hairline">
            {parsed.headers.map((h, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 px-4 py-2">
                <span className="min-w-[160px] flex-1 truncate text-caption text-cohere-ink">
                  Your column &ldquo;{h || `(column ${i + 1})`}&rdquo;
                </span>
                <ArrowRight className="h-3.5 w-3.5 shrink-0 text-slate-muted" aria-hidden="true" />
                <select
                  value={mapping[i] ?? ""}
                  onChange={(e) => setMapping((m) => ({ ...m, [i]: e.target.value }))}
                  aria-label={`Map column ${h || i + 1}`}
                  className="input-cohere w-auto min-w-[220px] px-2 py-1.5 text-caption"
                >
                  <option value="">Ignore this column</option>
                  {MAP_TARGETS.map((t) => (
                    <option
                      key={t.value}
                      value={t.value}
                      disabled={mappedValues.includes(t.value) && mapping[i] !== t.value}
                    >
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          {!titleMapped && (
            <p className="border-t border-hairline px-4 py-2.5 text-caption text-studio-maroon" role="alert">
              One of your columns must map to <code>title</code>. It&rsquo;s the only required column.
              Pick it above to continue.
            </p>
          )}
        </div>
      )}

      <InlineError error={props.error} />

      <button
        onClick={go}
        disabled={!csv.trim() || !titleMapped || props.loading}
        className="btn-primary mt-4 inline-flex items-center gap-2 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {props.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
        Parse & preview
      </button>
    </div>
  );
}

const EMPTY_MANUAL_ROW: Partial<ImportRow> = { country: "US" };

function ManualMode(props: { token: string; loading: boolean; setLoading: (b: boolean) => void;
  error: unknown; onError: (e: unknown) => void;
  onParsed: (b: BatchDetail) => void; onBack: () => void }) {
  // Multi-job batches: finished rows queue up here; `row` is the one being edited.
  const [queued, setQueued] = useState<Partial<ImportRow>[]>([]);
  const [row, setRow] = useState<Partial<ImportRow>>(EMPTY_MANUAL_ROW);
  function set<K extends keyof ImportRow>(k: K, v: ImportRow[K] | string) {
    setRow((r) => ({ ...r, [k]: v as never }));
  }
  const currentTitled = !!row.title_raw?.trim();
  const totalJobs = queued.length + (currentTitled ? 1 : 0);

  function addAnother() {
    if (!currentTitled) return;
    setQueued((q) => [...q, row]);
    setRow(EMPTY_MANUAL_ROW);
  }

  async function go() {
    const all = [...queued, ...(currentTitled ? [row] : [])];
    if (all.length === 0 || props.loading) return;
    props.setLoading(true); props.onError(null);
    try {
      const b = await importManual(props.token, all);
      props.onParsed(b);
    } catch (e: unknown) {
      props.onError(e);
    } finally {
      props.setLoading(false);
    }
  }
  return (
    <div className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
      <button onClick={props.onBack} className="mb-4 text-caption text-slate hover:text-cohere-ink">← Back</button>
      <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Enter jobs by hand</h2>
      <p className="mt-1 text-caption text-slate">
        Fill in a job, then add another or save. Every job you add here lands in one batch for review.
      </p>

      {queued.length > 0 && (
        <div className="mt-4 rounded-[10px] border border-hairline">
          <p className="px-4 py-2.5 text-caption font-medium text-cohere-ink">
            {queued.length} job{queued.length === 1 ? "" : "s"} added to this batch
          </p>
          <div className="divide-y divide-hairline border-t border-hairline">
            {queued.map((q, i) => (
              <div key={i} className="flex items-center justify-between gap-2 px-4 py-2">
                <p className="truncate text-caption text-cohere-ink">
                  {q.title_raw}
                  <span className="text-slate-muted">
                    {[q.city, q.state].filter(Boolean).length > 0
                      ? ` · ${[q.city, q.state].filter(Boolean).join(", ")}`
                      : ""}
                  </span>
                </p>
                <button
                  onClick={() => setQueued((prev) => prev.filter((_, ix) => ix !== i))}
                  aria-label={`Remove ${q.title_raw}`}
                  className="rounded-md border border-hairline p-1 text-slate-muted hover:border-studio-maroon hover:text-studio-maroon"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

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
      <InlineError error={props.error} />
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          onClick={addAnother}
          disabled={!currentTitled || props.loading}
          className="btn-pill-outline inline-flex items-center gap-1.5 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Plus className="h-4 w-4" /> Add another job
        </button>
        <button onClick={go} disabled={totalJobs === 0 || props.loading} className="btn-primary inline-flex items-center gap-2 disabled:cursor-not-allowed disabled:opacity-40">
          {props.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
          Save and preview{totalJobs > 1 ? ` (${totalJobs} jobs)` : ""}
        </button>
      </div>
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
  onSubmitted: (submittedCount: number) => void;
  onStartOver: () => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [note, setNote] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const staged = batch.rows.filter((r) => r.status === "staged");

  async function submit() {
    setSubmitting(true); setErr(null);
    const count = staged.length;
    try {
      await submitBatch(token, batch.id, note || undefined);
      onSubmitted(count);
    } catch (e: unknown) {
      setErr(e);
      setSubmitting(false);
    }
  }

  async function exclude(id: string) {
    await excludeRow(token, batch.id, id);
    const refreshed = { ...batch, rows: batch.rows.map((r) => r.id === id ? { ...r, status: "excluded" as const } : r) };
    onRefresh(refreshed);
  }

  async function restore(id: string) {
    await restoreRow(token, batch.id, id);
    const refreshed = { ...batch, rows: batch.rows.map((r) => r.id === id ? { ...r, status: "staged" as const } : r) };
    onRefresh(refreshed);
  }

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-cohere-blue/20 bg-wash-blue p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h2 className="text-[1.0625rem] font-medium text-cohere-ink">Preview before submit</h2>
            <p className="mt-1 text-body text-slate">
              <strong>{staged.length}</strong> job{staged.length === 1 ? "" : "s"} ready to send for SKILLED admin review.
              {batch.platform ? <> Detected platform: <span className="font-medium text-cohere-ink">{batch.platform}</span>.</> : null}
            </p>
          </div>
          <button onClick={onStartOver} className="text-caption text-slate hover:text-cohere-ink">Start over</button>
        </div>
      </div>

      {err != null && (
        <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4 text-body text-cohere-ink">
          {errText(err, "Could not submit this batch. Try again.")}
          <ErrorDetails error={err} />
        </div>
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
                onRestore={() => restore(r.id)}
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
            Submitting sends these to SKILLED admins. You&rsquo;ll be notified here when
            they review, usually within 1 business day.
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
  row, batchId, token, editing, onStartEdit, onStopEdit, onExclude, onRestore, onSaved,
}: {
  row: ImportRow; batchId: string; token: string; editing: boolean;
  onStartEdit: () => void; onStopEdit: () => void; onExclude: () => void;
  onRestore: () => void;
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
    <tr className={isDropped ? "opacity-60" : ""}>
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
          <span className="text-caption text-slate-muted">
            Excluded ·{" "}
            <button onClick={onRestore} className="text-cohere-blue underline">
              Undo
            </button>
          </span>
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
