"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Loader2 } from "lucide-react";

import { ImportBatch, listMyBatches } from "@/lib/api/jobImports";
import { PageHeader } from "@/components/ui";
import { StatusBadge } from "../[batchId]/StatusBadge";

export function MyBatchesClient({ token }: { token: string }) {
  const [batches, setBatches] = useState<ImportBatch[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    listMyBatches(token).then(setBatches).catch((e: Error) => setErr(e.message));
  }, [token]);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Job imports"
          title="My import batches"
          lead="Every batch you've submitted for SKILLED admin review. Approved batches publish to the live job board automatically."
          actions={
            <Link href="/employer/jobs/imports" className="btn-primary inline-flex items-center gap-1.5">
              <Plus className="h-4 w-4" /> New import
            </Link>
          }
        />

        {err && <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4 text-body">{err}</div>}

        {batches === null && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}

        {batches?.length === 0 && (
          <div className="rounded-xl border border-dashed border-hairline bg-white p-12 text-center">
            <p className="font-display text-feature text-cohere-ink">No batches yet</p>
            <p className="mt-2 text-body text-slate">Start your first import to add jobs to SKILLED.</p>
            <Link href="/employer/jobs/imports" className="btn-primary mt-4 inline-flex items-center gap-1.5">
              <Plus className="h-4 w-4" /> New import
            </Link>
          </div>
        )}

        {batches && batches.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-hairline bg-white shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
            <table className="w-full text-body">
              <thead className="border-b border-hairline bg-stone/40">
                <tr>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Source</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Submitted</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Rows</th>
                  <th className="px-4 py-3 text-left text-caption font-medium text-slate">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {batches.map((b) => (
                  <tr key={b.id}>
                    <td className="px-4 py-3">
                      <div className="font-medium text-cohere-ink capitalize">{b.source}</div>
                      {b.source_label && <div className="text-micro text-slate-muted truncate max-w-[280px]">{b.source_label}</div>}
                    </td>
                    <td className="px-4 py-3 text-caption text-slate">
                      {b.submitted_at ? new Date(b.submitted_at).toLocaleDateString() : <span className="text-slate-muted">Draft</span>}
                    </td>
                    <td className="px-4 py-3 text-caption text-slate">
                      {b.rows_total}
                      {b.status === "approved" || b.status === "published" ? <span className="text-slate-muted">, {b.rows_approved} published</span> : null}
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={b.status} /></td>
                    <td className="px-4 py-3 text-right">
                      <Link href={`/employer/jobs/imports/${b.id}`} className="text-caption text-cohere-blue underline">View</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
