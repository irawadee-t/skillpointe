"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Loader2, ArrowLeft, ChevronDown, ChevronUp,
  Check, X, CheckCircle2, XCircle,
} from "lucide-react";

import {
  BatchDetail, getAdminBatch, approveBatch, rejectBatch,
} from "@/lib/api/jobImports";
import { PageHeader } from "@/components/ui";
import { StatusBadge } from "../../../employer/jobs/imports/[batchId]/StatusBadge";

type Decision = "approve" | "reject";

export function AdminBatchClient({ token, batchId }: { token: string; batchId: string }) {
  const router = useRouter();
  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [working, setWorking] = useState(false);

  useEffect(() => {
    getAdminBatch(token, batchId).then((b) => {
      setBatch(b);
      const init: Record<string, Decision> = {};
      for (const r of b.rows) if (r.status === "staged") init[r.id] = "approve";
      setDecisions(init);
    }).catch((e: Error) => setErr(e.message));
  }, [token, batchId]);

  const counts = useMemo(() => {
    const out = { approve: 0, reject: 0 };
    for (const d of Object.values(decisions)) out[d]++;
    return out;
  }, [decisions]);

  const isPending = batch?.status === "pending";

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
    if (!note.trim()) { setErr("Please add a note explaining the rejection."); return; }
    setWorking(true); setErr(null);
    try {
      await rejectBatch(token, batch.id, note);
      router.push("/admin/job-imports");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not reject";
      setErr(msg); setWorking(false);
    }
  }

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
              title={batch.source_label || `${batch.source.toUpperCase()} import`}
              lead={`${batch.rows_total} jobs submitted${batch.submitted_at ? ` on ${new Date(batch.submitted_at).toLocaleDateString()}` : ""}${batch.platform ? `, platform: ${batch.platform}` : ""}.`}
              actions={<StatusBadge status={batch.status} />}
            />

            {isPending && (
              <div className="rounded-xl border border-cohere-blue/20 bg-wash-blue p-4 text-body text-cohere-ink">
                <strong>{counts.approve}</strong> approve, <strong>{counts.reject}</strong> reject — toggle per row, or approve/reject the full batch below.
              </div>
            )}

            <div className="overflow-hidden rounded-xl border border-hairline bg-white shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
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
                            <button onClick={() => setExpanded(isOpen ? null : r.id)} aria-label="Toggle details"
                              className="text-slate-muted hover:text-cohere-ink">
                              {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                            </button>
                          </td>
                          <td className="px-4 py-3 align-top">
                            <div className="font-medium text-cohere-ink">{r.title_raw}</div>
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
                            {isPending && r.status === "staged" ? (
                              <div className="inline-flex overflow-hidden rounded-full border border-hairline">
                                <button onClick={() => setDecisions((d) => ({ ...d, [r.id]: "approve" }))}
                                  aria-label="Approve" title="Approve"
                                  className={`px-2.5 py-1 ${dec === "approve" ? "bg-cohere-green text-white" : "text-slate hover:text-cohere-ink"}`}>
                                  <Check className="h-3.5 w-3.5" />
                                </button>
                                <button onClick={() => setDecisions((d) => ({ ...d, [r.id]: "reject" }))}
                                  aria-label="Reject" title="Reject"
                                  className={`px-2.5 py-1 border-l border-hairline ${dec === "reject" ? "bg-cohere-coral text-white" : "text-slate hover:text-cohere-ink"}`}>
                                  <X className="h-3.5 w-3.5" />
                                </button>
                              </div>
                            ) : (
                              <StatusBadge status={r.status} />
                            )}
                          </td>
                        </tr>
                        {isOpen && (
                          <tr className="bg-stone/30">
                            <td colSpan={5} className="px-6 py-4">
                              <div className="grid gap-4 lg:grid-cols-2">
                                <DetailField label="Description" value={r.description_raw} />
                                <DetailField label="Responsibilities" value={r.responsibilities_raw} />
                                <DetailField label="Requirements" value={r.requirements_raw} />
                                <DetailField label="Preferred" value={r.preferred_qualifications_raw} />
                                <DetailField label="Experience" value={r.experience_level} />
                                <DetailField label="Work setting" value={r.work_setting} />
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {isPending && (
              <div className="rounded-xl border border-hairline bg-white p-5 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
                <label className="mono-label mb-2 block">Note to employer (required if rejecting)</label>
                <textarea
                  value={note} onChange={(e) => setNote(e.target.value)}
                  rows={2}
                  placeholder="e.g. Three roles look duplicate of existing postings — please remove the marked rows."
                  className="input-cohere min-h-[64px] resize-y"
                />
                <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
                  <button onClick={reject} disabled={working}
                    className="btn-pill-outline inline-flex items-center gap-1.5 border-studio-maroon text-studio-maroon hover:bg-studio-maroon/[0.06]">
                    {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
                    Reject entire batch
                  </button>
                  <button onClick={approve} disabled={working || counts.approve === 0}
                    className="btn-primary inline-flex items-center gap-1.5">
                    {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                    {counts.reject === 0
                      ? `Approve all ${counts.approve}`
                      : `Approve ${counts.approve}, reject ${counts.reject}`}
                  </button>
                </div>
              </div>
            )}

            {!isPending && batch.reviewer_note && (
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

function DetailField({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div>
      <div className="mono-label mb-1">{label}</div>
      <p className="whitespace-pre-line text-caption text-slate leading-relaxed">{value}</p>
    </div>
  );
}
