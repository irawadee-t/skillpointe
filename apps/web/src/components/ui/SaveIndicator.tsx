"use client";

import { Loader2, Check, AlertTriangle } from "lucide-react";
import { formatRelative } from "@/lib/time";
import type { SaveStatus } from "@/lib/useAutosave";

/**
 * Tiny "saved 4s ago" line to sit next to a section heading, or in a page-level
 * corner. Matches the microcopy tone of the site.
 */
export function SaveIndicator({ status, lastSavedAt }: { status: SaveStatus; lastSavedAt: Date | null }) {
  if (status === "saving") {
    return (
      <span className="inline-flex items-center gap-1 text-micro text-slate-muted">
        <Loader2 className="h-3 w-3 animate-spin" /> Saving…
      </span>
    );
  }
  if (status === "saved") {
    return (
      <span className="inline-flex items-center gap-1 text-micro text-cohere-green">
        <Check className="h-3 w-3" /> Saved
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="inline-flex items-center gap-1 text-micro text-studio-maroon">
        <AlertTriangle className="h-3 w-3" /> Couldn't save — check your connection
      </span>
    );
  }
  if (lastSavedAt) {
    return (
      <span className="text-micro text-slate-muted">Saved {formatRelative(lastSavedAt.toISOString())}</span>
    );
  }
  return null;
}
