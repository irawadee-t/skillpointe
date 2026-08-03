"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Loader2, ArrowLeft, ChevronDown, ChevronUp,
  Check, X, CheckCircle2, XCircle, PauseCircle, AlertTriangle,
} from "lucide-react";

import {
  BatchDetail, ImportRow, RowDecision, batchDisplayTitle,
  getAdminBatch, approveBatch, rejectBatch,
} from "@/lib/api/jobImports";
import { PageHeader, statusChipClass } from "@/components/ui";
import { formatDateShort } from "@/lib/format";
import { ROW_STATUS_LABELS, WORK_SETTING_LABELS, humanizeEnum } from "@/lib/humanize";
import { ReviewStateChip } from "../ApprovalQueueClient";

/**
 * Batch review surface. Rows whose apply link failed validation default to
 * HOLD (a real decision, sent to the server) — the reviewer can override
 * per row. Row expansion leads with the structured extraction; the raw
 * scraped text sits behind a disclosure.
 */

export function AdminBatchClient({ token, batchId }: { token: string; batchId: string }) {
  const router = useRouter();
  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, RowDecision>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [working, setWorking] = useState(false);

  useEffect(() => {
    getAdminBatch(token, batchId).then((b) => {
      setBatch(b);
      const init: Record<string, RowDecision> = {};
      for (const r of b.rows) {
        if (r.status !== "staged") continue;
        // Broken/blocked apply links default to hold — mirror of the server
        // default, so what the reviewer sees is what will happen.
        init[r.id] = r.link_status === "broken" || r.link_status === "blocked"
          ? "hold" : "approve";
      }
      setDecisions(init);
    }).catch((e: Error) => setErr(e.message));
  }, [token, batchId]);

  const counts = useMemo(() => {
    const out = { approve: 0, reject: 0, hold: 0 };
    for (const d of Object.values(decisions)) out[d]++;
    return out;
  }, [decisions]);

  // Reviewable: submitted batches AND careers-page rolling drafts with
  // staged rows (the shared awaiting-review definition).
  const reviewable = batch?.status === "pending"
    || (batch?.review_state === "staged_from_careers");

  async function approve() {
    if (!batch) return;
    setWorking(true); setErr(null);
    try {
      await approveBatch(token, batch.id, note || undefined, decisions);
      router.push("/admin/job-imports");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not approve";
      setErr(msg); setWorking(false);
    }
  }

  async function reject() {
    if (!batch) return;
    if (note.trim().length < 3) {
      setErr("Add a note explaining the rejection. The employer needs a reason to act on.");
      return;
    }
    setWorking(true); setErr(null);
    try {
      await rejectBatch(token, batch.id, note);
      router.push("/admin/job-imports");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not reject";
      setErr(msg); setWorking(false);
    }
  }

  const rowsShown = batch?.rows.length ?? 0;
  const rowsTotal = batch?.rows_count ?? rowsShown;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Link href="/admin/job-imports" className="inline-flex items-center gap-1 text-caption text-slate hover:text-cohere-ink">
          <ArrowLeft className="h-3.5 w-3.5" /> Approval queue
        </Link>

        {err && <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4">{err}</div>}
        {batch === null && !err && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}

        {batch && (
          <>
            <PageHeader
              eyebrow={`Batch, ${batch.employer_name ?? batch.employer_id.slice(0, 8)}`}
              title={`${batch.employer_name ?? "Employer"} · ${batchDisplayTitle(batch)}`}
              lead={`${(batch.rows_staged ?? batch.rows_total).toLocaleString()} job${(batch.rows_staged ?? batch.rows_total) === 1 ? "" : "s"} to review${batch.submitted_at ? `, submitted ${formatDateShort(batch.submitted_at)}` : batch.review_state === "staged_from_careers" ? ", staged by the careers-page sync" : ""}${batch.platform ? ` · ${batch.platform}` : ""}.`}
              actions={<ReviewStateChip batch={batch} />}
            />

            {reviewable && (
              <div className="rounded-xl border border-cohere-blue/20 bg-wash-blue p-4 text-body text-cohere-ink">
                <strong>{counts.approve}</strong> approve · <strong>{counts.hold}</strong> hold ·{" "}
                <strong>{counts.reject}</strong> reject. Toggle per row.
                {counts.hold > 0 && (
                  <span className="mt-1 block text-caption text-slate">
                    Held rows stay unpublished until their apply link is fixed or you
                    approve them explicitly. The employer sees an honest partial outcome.
                  </span>
                )}
              </div>
            )}

            <div className="overflow-hidden rounded-xl border border-hairline bg-white">
              <table className="w-full text-body">
                <thead className="border-b border-hairline bg-stone/40">
                  <tr>
                    <th className="w-8 px-3 py-3" />
                    <th className="px-4 py-3 text-left text-caption font-medium text-slate">Title</th>
                    <th className="px-4 py-3 text-left text-caption font-medium text-slate">Location</th>
                    <th className="px-4 py-3 text-left text-caption font-medium text-slate">Pay</th>
                    <th className="px-4 py-3 text-right text-caption font-medium text-slate">Decision</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {batch.rows.map((r) => {
                    const dec = decisions[r.id];
                    const isOpen = expanded === r.id;
                    return (
                      <Fragment key={r.id}>
                        <tr className={dec === "reject" ? "bg-studio-maroon/[0.04]" : ""}>
                          <td className="px-3 py-3 align-top">
                            <button onClick={() => setExpanded(isOpen ? null : r.id)}
                              aria-label="Toggle details" aria-expanded={isOpen}
                              className="text-slate-muted hover:text-cohere-ink">
                              {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                            </button>
                          </td>
                          <td className="px-4 py-3 align-top">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="font-medium text-cohere-ink">{r.title_raw}</span>
                              <LinkStatusChip row={r} />
                            </div>
                            {r.source_url && (
                              <a href={r.source_url} target="_blank" rel="noopener noreferrer"
                                className="mt-0.5 block max-w-[280px] truncate text-micro text-cohere-blue underline">
                                {r.source_url}
                              </a>
                            )}
                          </td>
                          <td className="px-4 py-3 align-top text-caption text-slate">
                            {[r.city, r.state].filter(Boolean).join(", ") || "—"}
                          </td>
                          <td className="px-4 py-3 align-top text-caption text-slate">
                            {r.pay_raw || (r.pay_min ? `$${r.pay_min}${r.pay_max ? `–$${r.pay_max}` : ""}` : "—")}
                          </td>
                          <td className="px-4 py-3 align-top text-right">
                            {reviewable && r.status === "staged" ? (
                              <div className="inline-flex overflow-hidden rounded-full border border-hairline" role="group" aria-label={`Decision for ${r.title_raw}`}>
                                <button onClick={() => setDecisions((d) => ({ ...d, [r.id]: "approve" }))}
                                  aria-label="Approve" aria-pressed={dec === "approve"} title="Approve and publish"
                                  className={`px-2.5 py-1 ${dec === "approve" ? "bg-cohere-green text-white" : "text-slate hover:text-cohere-ink"}`}>
                                  <Check className="h-3.5 w-3.5" />
                                </button>
                                <button onClick={() => setDecisions((d) => ({ ...d, [r.id]: "hold" }))}
                                  aria-label="Hold" aria-pressed={dec === "hold"} title="Hold: park until the apply link is fixed"
                                  className={`border-l border-hairline px-2.5 py-1 ${dec === "hold" ? "bg-studio-maroon text-white" : "text-slate hover:text-cohere-ink"}`}>
                                  <PauseCircle className="h-3.5 w-3.5" />
                                </button>
                                <button onClick={() => setDecisions((d) => ({ ...d, [r.id]: "reject" }))}
                                  aria-label="Reject" aria-pressed={dec === "reject"} title="Reject this row"
                                  className={`border-l border-hairline px-2.5 py-1 ${dec === "reject" ? "bg-ink text-white" : "text-slate hover:text-cohere-ink"}`}>
                                  <X className="h-3.5 w-3.5" />
                                </button>
                              </div>
                            ) : (
                              <RowStatusChip status={r.status} />
                            )}
                          </td>
                        </tr>
                        {isOpen && (
                          <tr className="bg-stone/30">
                            <td colSpan={5} className="px-6 py-4">
                              <RowExpansion row={r} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <p className="text-caption text-slate">
              Showing {rowsShown.toLocaleString()} of {rowsTotal.toLocaleString()} rows
              {batch.rows_by_status && Object.keys(batch.rows_by_status).length > 0 && (
                <>: {Object.entries(batch.rows_by_status)
                  .map(([s, c]) => `${c} ${humanizeEnum(s, ROW_STATUS_LABELS).toLowerCase()}`)
                  .join(" · ")}</>
              )}
            </p>

            {reviewable && (
              <div className="rounded-xl border border-hairline bg-white p-5">
                <label htmlFor="reviewer-note" className="mono-label mb-2 block">Note to employer (required if rejecting)</label>
                <textarea
                  id="reviewer-note"
                  value={note} onChange={(e) => setNote(e.target.value)}
                  rows={2}
                  placeholder="e.g. Three roles look duplicate of existing postings. Please remove the marked rows."
                  className="input-cohere min-h-[64px] resize-y"
                />
                <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
                  <button onClick={reject} disabled={working}
                    className="btn-pill-outline inline-flex items-center gap-1.5 border-studio-maroon text-studio-maroon hover:bg-studio-maroon/[0.06]">
                    {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                    Reject entire batch
                  </button>
                  <button onClick={approve} disabled={working || (counts.approve + counts.hold + counts.reject) === 0}
                    className="btn-primary inline-flex items-center gap-1.5">
                    {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                    {approveLabel(counts)}
                  </button>
                </div>
              </div>
            )}

            {/* Reviewer note: green wash ONLY for a real note on an approved
                batch — rejected notes read as attention, and absent/trivial
                notes get no celebratory panel at all. */}
            {!reviewable && meaningfulNote(batch.reviewer_note) && (
              <div className={`rounded-xl border p-5 ${batch.status === "rejected" ? "border-studio-maroon/30 bg-studio-maroon/[0.06]" : "border-cohere-green/30 bg-wash-green"}`}>
                <div className="mono-label mb-1">Reviewer note</div>
                <p className="text-body text-cohere-ink">{batch.reviewer_note}</p>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}

function approveLabel(counts: { approve: number; reject: number; hold: number }): string {
  const parts: string[] = [];
  if (counts.approve) parts.push(`publish ${counts.approve}`);
  if (counts.hold) parts.push(`hold ${counts.hold}`);
  if (counts.reject) parts.push(`reject ${counts.reject}`);
  if (parts.length === 0) return "Nothing to submit";
  const label = parts.join(", ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function meaningfulNote(note: string | null | undefined): boolean {
  return Boolean(note && note.trim().length >= 3);
}

/** Row-level attention chip for apply-link health — visible in the table. */
function LinkStatusChip({ row }: { row: ImportRow }) {
  if (row.link_status === "broken") {
    return (
      <span className={statusChipClass("danger")}>
        <AlertTriangle className="h-3 w-3" aria-hidden /> Apply link broken
      </span>
    );
  }
  if (row.link_status === "blocked") {
    return (
      <span className={statusChipClass("attention")}>
        <AlertTriangle className="h-3 w-3" aria-hidden /> Apply link blocked
      </span>
    );
  }
  if (row.status === "stale") {
    return <span className={statusChipClass("attention")}>No longer on source</span>;
  }
  return null;
}

/** Honest row-status chips — every state named, no silent Draft fallback. */
function RowStatusChip({ status }: { status: ImportRow["status"] }) {
  const tone = status === "published" ? "positive"
    : status === "held" || status === "stale" ? "attention"
    : status === "staged" ? "progress"
    : "muted";
  return (
    <span className={statusChipClass(tone)}>
      {humanizeEnum(status, ROW_STATUS_LABELS)}
    </span>
  );
}

/**
 * Expansion leads with the STRUCTURED extraction (family, pay parse,
 * location, link check); the raw scraped text is behind a disclosure.
 */
function RowExpansion({ row }: { row: ImportRow }) {
  const [showRaw, setShowRaw] = useState(false);
  const structured: Array<[string, string | null]> = [
    ["Job family", row.job_category ?? null],
    ["Pay parse", row.pay_min != null
      ? `$${row.pay_min}${row.pay_max != null ? ` – $${row.pay_max}` : ""}${row.pay_type ? ` ${humanizeEnum(row.pay_type).toLowerCase()}` : ""}`
      : row.pay_raw ? `Unparsed: "${row.pay_raw}"` : null],
    ["Location", [row.city, row.state].filter(Boolean).join(", ") || null],
    ["Work setting", row.work_setting ? humanizeEnum(row.work_setting, WORK_SETTING_LABELS) : null],
    ["Experience", row.experience_level ? humanizeEnum(row.experience_level) : null],
    ["Employment type", row.employment_type ? humanizeEnum(row.employment_type) : null],
    ["Apply link check", row.link_status
      ? `${humanizeEnum(row.link_status)}${row.link_checked_at ? ` (checked ${formatDateShort(row.link_checked_at)})` : ""}`
      : "Not checked"],
    ["Posted", row.posted_date ?? null],
  ];
  const hasRaw = Boolean(row.description_raw || row.responsibilities_raw
    || row.requirements_raw || row.preferred_qualifications_raw);
  return (
    <div className="space-y-4">
      <div>
        <div className="mono-label mb-2">Structured extraction</div>
        <dl className="grid gap-x-8 gap-y-1.5 sm:grid-cols-2 lg:grid-cols-3">
          {structured.filter(([, v]) => v).map(([k, v]) => (
            <div key={k} className="flex items-baseline gap-2">
              <dt className="shrink-0 text-caption text-slate-muted">{k}</dt>
              <dd className="text-caption text-cohere-ink">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
      {hasRaw && (
        <div>
          <button
            onClick={() => setShowRaw((v) => !v)}
            aria-expanded={showRaw}
            className="inline-flex items-center gap-1 text-caption text-slate underline hover:text-cohere-ink"
          >
            {showRaw ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            {showRaw ? "Hide raw scraped text" : "Show raw scraped text"}
          </button>
          {showRaw && (
            <div className="mt-3 grid gap-4 lg:grid-cols-2">
              <DetailField label="Description" value={row.description_raw} />
              <DetailField label="Responsibilities" value={row.responsibilities_raw} />
              <DetailField label="Requirements" value={row.requirements_raw} />
              <DetailField label="Preferred" value={row.preferred_qualifications_raw} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DetailField({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div>
      <div className="mono-label mb-1">{label}</div>
      <p className="whitespace-pre-line text-caption text-slate leading-relaxed">{value}</p>
    </div>
  );
}
