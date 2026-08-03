"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Small typeahead hook — debounces the query string, calls the fetcher, tracks
 * loading + error state. No caching. Cancels in-flight requests when a newer
 * query comes in via AbortController.
 *
 * Usage:
 *   const { results, loading, error } = useTypeahead(query, async (q, signal) => {
 *     const r = await fetch(`/api/search/applicants?q=${encodeURIComponent(q)}`, { signal });
 *     if (!r.ok) throw new Error("search failed");
 *     return (await r.json()) as Applicant[];
 *   }, { minChars: 2, debounceMs: 180 });
 */
export function useTypeahead<T>(
  query: string,
  fetcher: (q: string, signal: AbortSignal) => Promise<T[]>,
  {
    minChars = 1,
    debounceMs = 250,
  }: { minChars?: number; debounceMs?: number } = {},
) {
  const [results, setResults] = useState<T[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (q.length < minChars) {
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    // Cancel any in-flight request from a prior keystroke.
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const timer = setTimeout(async () => {
      try {
        const data = await fetcher(q, controller.signal);
        if (!controller.signal.aborted) setResults(data);
      } catch (e) {
        if (controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : "Search failed");
        setResults([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, debounceMs);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // fetcher intentionally excluded — parents typically inline a closure that
    // changes every render; we key on the query string.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, minChars, debounceMs]);

  return { results, loading, error };
}
