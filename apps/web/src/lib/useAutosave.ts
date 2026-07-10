"use client";

import { useEffect, useRef, useState } from "react";

export type SaveStatus = "idle" | "saving" | "saved" | "error";

/**
 * Debounced autosave hook. Watches a value; when it changes, waits for
 * `delay` ms of quiet, then calls `save(value)`. Skips the initial mount so
 * we don't PATCH the profile with what we just loaded.
 *
 *   const status = useAutosave(form, 800, async (next) => { await patch(next); });
 *
 * Returns a status you render next to the section title:
 *   idle | saving | saved | error
 */
export function useAutosave<T>(
  value: T,
  delayMs: number,
  save: (value: T) => Promise<unknown>,
): { status: SaveStatus; lastSavedAt: Date | null } {
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const firstRun = useRef(true);
  const latest = useRef(value);
  latest.current = value;

  useEffect(() => {
    if (firstRun.current) { firstRun.current = false; return; }
    setStatus("saving");
    const t = setTimeout(async () => {
      try {
        await save(latest.current);
        setStatus("saved");
        setLastSavedAt(new Date());
        // fade back to idle after 3s
        const idleT = setTimeout(() => setStatus("idle"), 3000);
        return () => clearTimeout(idleT);
      } catch {
        setStatus("error");
      }
    }, delayMs);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(value)]);

  return { status, lastSavedAt };
}
