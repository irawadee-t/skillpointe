"use client";

import { useEffect, useState } from "react";

import { readViewAsClient, type ViewAsTarget } from "@/lib/viewAs";

/**
 * Client hook for admin "view as applicant" debug mode.
 *
 * Returns the active view-as target (or null). Action controls in applicant
 * UI should render disabled with title="Read-only in view-as" when active —
 * the backend independently 403s every mutation, this is just honest UI.
 *
 * Reads the cookie after mount so server + client markup match (null on first
 * paint, then hydrates to the real value).
 */
export function useViewAs(): { viewAs: ViewAsTarget | null; isViewAs: boolean } {
  const [viewAs, setViewAs] = useState<ViewAsTarget | null>(null);

  useEffect(() => {
    setViewAs(readViewAsClient());
  }, []);

  return { viewAs, isViewAs: viewAs !== null };
}

export const VIEW_AS_READONLY_TOOLTIP = "Read-only in view-as";
