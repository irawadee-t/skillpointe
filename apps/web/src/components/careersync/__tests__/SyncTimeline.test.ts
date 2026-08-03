import { describe, expect, it } from "vitest";

import { syncSentence } from "../SyncTimeline";
import type { CareerSourcePullHistoryItem } from "@/lib/api/careerSource";

function pull(over: Partial<CareerSourcePullHistoryItem> = {}): CareerSourcePullHistoryItem {
  return {
    pull_id: "p1",
    batch_id: "b1",
    status: "ok",
    platform: "generic",
    error: null,
    jobs_found: 25,
    jobs_new: 0,
    jobs_updated: 0,
    jobs_removed: 0,
    jobs_rejected: 0,
    links_broken: 0,
    sync_mode: "incremental",
    duration_ms: 1200,
    fetch_count: 1,
    details: {},
    created_at: new Date().toISOString(),
    triggered_by: null,
    ...over,
  };
}

describe("syncSentence", () => {
  it("says removal detection is off when the crawl never reached the last page", () => {
    const s = syncSentence(pull({
      details: {
        removal_detection: "skipped_incomplete",
        listing_complete: false,
        listing_pages: 1,
        removal_note: "Checked the first 25 listings on this site. Removal detection stays off until a scan reaches the last page.",
      },
    }));
    expect(s.parts.join(", ")).toContain("removal detection off until a scan reaches the last page");
    // A partial crawl must never read as a clean, complete sync.
    expect(s.parts.join(", ")).not.toContain("removed");
  });

  it("states the held numbers instead of reporting zero removals", () => {
    const s = syncSentence(pull({
      details: {
        removal_detection: "held_for_review",
        listing_complete: true,
        removal_hold: { would_remove: 74, live: 83 },
      },
    }));
    expect(s.headline).toContain("Held for review");
    expect(s.parts.join(", ")).toContain("74 of 83 live jobs");
    expect(s.parts.join(", ")).toContain("nothing was removed");
    expect(s.tone).toBe("error");
  });

  it("reports a normal sync unchanged when removals were applied", () => {
    const s = syncSentence(pull({
      jobs_new: 2,
      jobs_removed: 1,
      details: {
        removal_detection: "applied",
        listing_complete: true,
        added: [{ title: "Welder II" }, { title: "Millwright" }],
        removed: [{ title: "CNC Machinist" }],
      },
    }));
    expect(s.parts.join(", ")).toContain("2 added (Welder II, Millwright)");
    expect(s.parts.join(", ")).toContain("1 removed (CNC Machinist");
    expect(s.parts.join(", ")).not.toContain("removal detection off");
  });
});
