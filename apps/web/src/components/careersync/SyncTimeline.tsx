"use client";

/**
 * Sync activity timeline for a connected careers page — shared between the
 * employer imports hub and the admin career-sources console.
 *
 * Renders one plain-English sentence per sync event, e.g.
 *   "9:14 AM — Synced in 1.2s: 2 jobs added (Welder II, Extruder Operator),
 *    1 removed (CNC Machinist — no longer on site), 14 unchanged"
 *
 * Design contract v2: white sheet, hairline rows, sentence case, relative
 * timestamps, quiet type. No cards-of-cards, no icon circles.
 */
import type {
  CareerSourcePullHistoryItem,
  PullDetailEntry,
} from "@/lib/api/careerSource";

export function relativeTime(iso: string): string {
  const secs = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (secs < 45) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function absoluteTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function duration(ms?: number | null): string | null {
  if (ms == null || ms <= 0) return null;
  if (ms < 1000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

function titleList(entries?: PullDetailEntry[], more?: number): string {
  if (!entries || entries.length === 0) return "";
  const shown = entries.slice(0, 4).map((e) => e.title).join(", ");
  const extra = (entries.length > 4 ? entries.length - 4 : 0) + (more ?? 0);
  return extra > 0 ? `${shown} and ${extra} more` : shown;
}

/** One-sentence summary of what a sync did. */
export function syncSentence(p: CareerSourcePullHistoryItem): {
  headline: string;
  parts: string[];
  tone: "ok" | "quiet" | "error";
} {
  const dur = duration(p.duration_ms);
  const d = p.details ?? {};

  if (p.status === "error" || p.status === "blocked") {
    return {
      headline: `Sync failed${p.error ? `: ${p.error}` : ""}`,
      parts: [],
      tone: "error",
    };
  }
  if (p.status === "no_jobs") {
    return {
      headline: "Sync found no job postings at this address",
      parts: [], tone: "error",
    };
  }
  if (p.sync_mode === "not_modified") {
    return {
      headline: `Checked the site${dur ? ` in ${dur}` : ""}, nothing changed`,
      parts: d.unchanged ? [`${d.unchanged} job${d.unchanged === 1 ? "" : "s"} still live`] : [],
      tone: "quiet",
    };
  }

  // Removal detection is only trustworthy on a crawl that reached the last
  // page, and a very large removal set is held for a human either way. Both
  // states are stated outright rather than shown as "0 removed".
  const removalHold = d.removal_hold;
  if (d.removal_detection === "held_for_review" && removalHold) {
    return {
      headline: `Held for review${dur ? ` after ${dur}` : ""}`,
      parts: [
        `${removalHold.would_remove} of ${removalHold.live} live jobs would have been removed in one pass`,
        "nothing was removed",
      ],
      tone: "error",
    };
  }

  const parts: string[] = [];
  if (p.jobs_new > 0) {
    const t = titleList(d.added, d.added_more);
    parts.push(`${p.jobs_new} added${t ? ` (${t})` : ""}`);
  }
  if (p.jobs_updated > 0) {
    const t = titleList(d.updated, d.updated_more);
    parts.push(`${p.jobs_updated} updated${t ? ` (${t})` : ""}`);
  }
  if (p.jobs_removed > 0) {
    const t = titleList(d.removed, d.removed_more);
    parts.push(`${p.jobs_removed} removed${t ? ` (${t}, no longer on the site)` : ""}`);
  }
  if (d.restored && d.restored.length > 0) {
    parts.push(`${d.restored.length} back on the site (${titleList(d.restored)})`);
  }
  if (typeof d.unchanged === "number" && d.unchanged > 0) {
    parts.push(`${d.unchanged} unchanged`);
  }
  if (p.links_broken > 0) {
    const t = titleList(d.held);
    parts.push(`${p.links_broken} held for review${t ? ` (${t}, apply link not working)` : " (broken apply links)"}`);
  }
  if (p.jobs_rejected > 0) parts.push(`${p.jobs_rejected} not trades roles`);
  if (d.removal_detection === "skipped_incomplete") {
    parts.push("removal detection off until a scan reaches the last page");
  }

  let headline: string;
  if (p.sync_mode === "relearned") {
    headline = `Site structure changed. Relearned the page layout${dur ? `, synced in ${dur}` : ""}`;
  } else if (p.sync_mode === "full") {
    headline = `Full scan${dur ? ` in ${dur}` : ""}: ${p.jobs_found} job${p.jobs_found === 1 ? "" : "s"} found on the site`;
  } else {
    headline = `Synced${dur ? ` in ${dur}` : ""}`;
  }
  if (parts.length === 0 && p.sync_mode === "incremental") {
    parts.push("no changes");
  }
  return { headline, parts, tone: p.jobs_new > 0 || p.jobs_removed > 0 ? "ok" : "quiet" };
}

export function SyncTimeline({
  pulls,
  emptyText = "No syncs yet. Pull from the site to start the log.",
}: {
  pulls: CareerSourcePullHistoryItem[];
  emptyText?: string;
}) {
  if (pulls.length === 0) {
    return <p className="px-5 py-3.5 text-caption text-slate-muted">{emptyText}</p>;
  }
  return (
    <ul>
      {pulls.map((p) => {
        const s = syncSentence(p);
        return (
          <li
            key={p.pull_id ?? p.created_at}
            className="flex gap-4 border-t border-hairline px-5 py-3.5 first:border-t-0"
          >
            <span
              className="w-20 shrink-0 pt-px text-caption tabular-nums text-slate-muted"
              title={absoluteTime(p.created_at)}
            >
              {relativeTime(p.created_at)}
            </span>
            <div className="min-w-0">
              <p className={`text-caption ${s.tone === "error" ? "text-studio-maroon" : "text-cohere-ink"}`}>
                {s.headline}
                {s.parts.length > 0 && (
                  <span className="text-slate">{": "}{s.parts.join(", ")}</span>
                )}
              </p>
              <p className="mt-0.5 text-micro text-slate-muted">
                {p.triggered_by ? "Manual refresh" : "Auto-sync"}
                {typeof p.fetch_count === "number" ? ` · ${p.fetch_count} request${p.fetch_count === 1 ? "" : "s"} to the site` : ""}
                {typeof p.details?.listing_pages === "number" && p.details.listing_pages > 1
                  ? ` · ${p.details.listing_pages} listing pages read`
                  : ""}
                {p.details?.note && !p.details?.relearned ? ` · ${p.details.note}` : ""}
              </p>
              {p.details?.removal_note && (
                <p className="mt-0.5 text-micro text-slate">{p.details.removal_note}</p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
