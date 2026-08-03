"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { AuditLogList, fetchAuditLogs } from "@/lib/api/admin";
import { Breadcrumb, PageHeader } from "@/components/ui";
import { humanizeEnum } from "@/lib/humanize";

const PAGE_SIZE = 50;

export function AuditLogClient({ token }: { token: string }) {
  const [data, setData] = useState<AuditLogList | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    try {
      setData(await fetchAuditLogs(token, {
        action: action || undefined,
        entityType: entityType || undefined,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        limit: PAGE_SIZE,
        offset,
      }));
      setErr(null);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not load the audit log");
    }
  }, [token, action, entityType, dateFrom, dateTo, offset]);

  useEffect(() => { void load(); }, [load]);

  const items = data?.items ?? null;
  const total = data?.total ?? 0;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Audit log" }]} />
        <PageHeader
          eyebrow="Operations"
          title="Audit log"
          lead="Read-only trail of every privileged action: who did what, to which entity, when. Filter by action, entity, or date."
        />

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-caption text-slate">
            Action
            <select
              value={action}
              onChange={(e) => { setAction(e.target.value); setOffset(0); }}
              className="rounded-[8px] border border-hairline bg-white px-2.5 py-1.5 text-body text-cohere-ink focus:outline-2 focus:outline-studio-maroon"
            >
              <option value="">All actions</option>
              {(data?.actions ?? []).map((a) => (
                <option key={a} value={a}>{humanizeEnum(a)}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-caption text-slate">
            Entity
            <select
              value={entityType}
              onChange={(e) => { setEntityType(e.target.value); setOffset(0); }}
              className="rounded-[8px] border border-hairline bg-white px-2.5 py-1.5 text-body text-cohere-ink focus:outline-2 focus:outline-studio-maroon"
            >
              <option value="">All entities</option>
              {(data?.entity_types ?? []).map((t) => (
                <option key={t} value={t}>{humanizeEnum(t)}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-caption text-slate">
            From
            <input
              type="date" value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setOffset(0); }}
              className="rounded-[8px] border border-hairline bg-white px-2.5 py-1.5 text-body text-cohere-ink focus:outline-2 focus:outline-studio-maroon"
            />
          </label>
          <label className="flex flex-col gap-1 text-caption text-slate">
            To
            <input
              type="date" value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setOffset(0); }}
              className="rounded-[8px] border border-hairline bg-white px-2.5 py-1.5 text-body text-cohere-ink focus:outline-2 focus:outline-studio-maroon"
            />
          </label>
        </div>

        {err && (
          <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4 text-body text-cohere-ink">{err}</div>
        )}
        {items === null && !err && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}

        {items?.length === 0 && (
          <div className="rounded-[10px] border border-hairline bg-white px-5 py-3.5">
            <p className="text-body text-slate">No audit entries match these filters.</p>
          </div>
        )}

        {items && items.length > 0 && (
          <>
            <div className="overflow-x-auto rounded-xl border border-hairline bg-white">
              <table className="w-full text-body">
                <thead className="border-b border-hairline bg-stone/40">
                  <tr>
                    <th className="px-4 py-3 text-left text-caption font-medium text-slate">When</th>
                    <th className="px-4 py-3 text-left text-caption font-medium text-slate">Actor</th>
                    <th className="px-4 py-3 text-left text-caption font-medium text-slate">Action</th>
                    <th className="px-4 py-3 text-left text-caption font-medium text-slate">Entity</th>
                    <th className="px-4 py-3 text-left text-caption font-medium text-slate">Note</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {items.map((r) => (
                    <tr key={r.id}>
                      <td className="whitespace-nowrap px-4 py-3 text-caption tabular-nums text-slate">
                        {new Date(r.created_at).toLocaleString(undefined, {
                          month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
                        })}
                      </td>
                      <td className="px-4 py-3 text-caption text-slate">
                        {r.actor_role ? humanizeEnum(r.actor_role) : "System"}
                        {r.actor_id && (
                          <span className="ml-1 text-micro text-slate-muted" title={r.actor_id}>
                            {r.actor_id.slice(0, 8)}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-medium text-cohere-ink">{humanizeEnum(r.action)}</td>
                      <td className="px-4 py-3 text-caption text-slate">
                        {r.entity_type ? humanizeEnum(r.entity_type) : "—"}
                        {r.entity_id && (
                          <span className="ml-1 text-micro text-slate-muted" title={r.entity_id}>
                            {r.entity_id.slice(0, 8)}
                          </span>
                        )}
                      </td>
                      <td className="max-w-[320px] px-4 py-3 text-caption text-slate">
                        <span className="line-clamp-2">{r.note ?? "—"}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between text-caption text-slate">
              <span>Showing {Math.min(offset + 1, total)}–{Math.min(offset + PAGE_SIZE, total)} of {total.toLocaleString()}</span>
              <div className="flex gap-2">
                <button
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  disabled={offset === 0}
                  className="rounded-full border border-hairline bg-white px-3 py-1 transition-colors hover:border-cohere-ink disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  disabled={offset + PAGE_SIZE >= total}
                  className="rounded-full border border-hairline bg-white px-3 py-1 transition-colors hover:border-cohere-ink disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
