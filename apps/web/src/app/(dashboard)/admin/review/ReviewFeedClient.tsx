"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CheckCircle2, ExternalLink, Loader2 } from "lucide-react";

import {
  ReviewFeed, ReviewItem, fetchReviewFeed, resolveReviewItem,
} from "@/lib/api/admin";
import { Breadcrumb, PageHeader, statusChipClass, useToast } from "@/components/ui";
import { REVIEW_ITEM_TYPE_LABELS, humanizeEnum } from "@/lib/humanize";
import { formatDateShort } from "@/lib/format";

const PAGE_SIZE = 50;

export function ReviewFeedClient({ token }: { token: string }) {
  const toast = useToast();
  const [feed, setFeed] = useState<ReviewFeed | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setFeed(await fetchReviewFeed(token, {
        itemType: typeFilter ?? undefined, limit: PAGE_SIZE, offset,
      }));
      setErr(null);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Could not load the review feed");
    }
  }, [token, typeFilter, offset]);

  useEffect(() => { void load(); }, [load]);

  async function act(item: ReviewItem, action: "reviewed" | "dismissed") {
    setBusyId(item.id);
    try {
      await resolveReviewItem(token, item.id, action);
      toast.success(action === "dismissed" ? "Flag dismissed." : "Marked as reviewed.");
      await load();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Could not update the item");
    } finally {
      setBusyId(null);
    }
  }

  const typeCounts = useMemo(
    () => Object.entries(feed?.pending_by_type ?? {}).sort((a, b) => b[1] - a[1]),
    [feed],
  );
  const items = feed?.items ?? null;
  const total = feed?.total ?? 0;

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Review" }]} />
        <PageHeader
          eyebrow="Operations"
          title="Review"
          lead={
            feed
              ? `${feed.pending_total.toLocaleString()} item${feed.pending_total === 1 ? "" : "s"} pending: guardrail trips, ambiguous credentials, broken apply links, and anything else the pipelines flagged for a human.`
              : "Everything the pipelines flagged for a human decision, in one prioritized queue."
          }
        />

        {typeCounts.length > 0 && (
          <div className="flex flex-wrap gap-2 border-b border-hairline pb-3" role="tablist" aria-label="Item types">
            <button
              role="tab"
              aria-selected={typeFilter === null}
              onClick={() => { setTypeFilter(null); setOffset(0); }}
              className={`rounded-full border px-3 py-1 text-caption transition-colors ${
                typeFilter === null
                  ? "border-ink bg-ink text-white"
                  : "border-hairline bg-white text-slate hover:border-cohere-ink hover:text-cohere-ink"
              }`}
            >
              All <span className="ml-1 tabular-nums">{feed?.pending_total}</span>
            </button>
            {typeCounts.map(([t, c]) => (
              <button
                key={t}
                role="tab"
                aria-selected={typeFilter === t}
                onClick={() => { setTypeFilter(t); setOffset(0); }}
                className={`rounded-full border px-3 py-1 text-caption transition-colors ${
                  typeFilter === t
                    ? "border-ink bg-ink text-white"
                    : "border-hairline bg-white text-slate hover:border-cohere-ink hover:text-cohere-ink"
                }`}
              >
                {humanizeEnum(t, REVIEW_ITEM_TYPE_LABELS)}
                <span className="ml-1 tabular-nums">{c}</span>
              </button>
            ))}
          </div>
        )}

        {err && (
          <div className="rounded-xl border border-studio-maroon/30 bg-studio-maroon/[0.06] p-4 text-body text-cohere-ink">{err}</div>
        )}
        {items === null && !err && (
          <div className="flex items-center gap-2 text-body text-slate"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
        )}

        {items?.length === 0 && (
          <div className="flex items-center gap-3 rounded-md border border-hairline bg-white p-6" data-tour-id="review-feed">
            <CheckCircle2 className="h-5 w-5 text-cohere-green" strokeWidth={1.75} />
            <p className="text-body text-cohere-ink">Nothing pending. The pipelines have no open flags.</p>
          </div>
        )}

        {items && items.length > 0 && (
          <>
            <ul className="divide-y divide-hairline overflow-hidden rounded-md border border-hairline bg-white" data-tour-id="review-feed">
              {items.map((item) => (
                <li key={item.id} className="flex flex-wrap items-start gap-4 p-5">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={statusChipClass(item.priority <= 3 ? "attention" : "neutral")}>
                        {humanizeEnum(item.item_type, REVIEW_ITEM_TYPE_LABELS)}
                      </span>
                      {item.confidence_level && (
                        <span className="text-micro text-slate-muted">
                          {humanizeEnum(item.confidence_level)} confidence
                        </span>
                      )}
                      <span className="text-micro text-slate-muted">
                        {formatDateShort(item.created_at)}
                      </span>
                    </div>
                    <p className="mt-1.5 text-body text-cohere-ink">
                      {item.description || `${humanizeEnum(item.entity_type)} ${item.entity_id.slice(0, 8)} needs a look.`}
                    </p>
                    {item.link_href && (
                      <Link
                        href={item.link_href}
                        className="mt-1 inline-flex items-center gap-1 text-caption text-cohere-blue underline"
                      >
                        Open resolution surface <ExternalLink className="h-3 w-3" aria-hidden />
                      </Link>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      onClick={() => act(item, "reviewed")}
                      disabled={busyId === item.id}
                      className="btn-pill-outline inline-flex items-center gap-1 text-caption disabled:opacity-40"
                    >
                      {busyId === item.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                      Resolve
                    </button>
                    <button
                      onClick={() => act(item, "dismissed")}
                      disabled={busyId === item.id}
                      className="text-caption text-slate underline hover:text-cohere-ink disabled:opacity-40"
                    >
                      Dismiss
                    </button>
                  </div>
                </li>
              ))}
            </ul>

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
