"use client";

import { useEffect, useRef } from "react";
import { createClient } from "@/lib/supabase/client";

/**
 * useRealtimeChannel — thin wrapper around Supabase Realtime.
 *
 * Subscribes to a postgres_changes event on the given channel, invokes
 * `onEvent` with the raw payload on every matching change, and cleans up
 * on unmount or when `enabled` flips false.
 *
 * The `event` string is passed straight through to the postgres_changes
 * filter (e.g. "INSERT", "UPDATE", "DELETE", "*"). If you need a table
 * or row-level filter, pass it via `filter` — e.g. `table=direct_messages`
 * and `filter="conversation_id=eq.<uuid>"`.
 *
 * Kept intentionally small — the specific rooms (messages inbox, thread,
 * notifications) wire this up with their own refetch handlers on top.
 */
export function useRealtimeChannel(
  channel: string,
  event: "INSERT" | "UPDATE" | "DELETE" | "*",
  onEvent: (payload: unknown) => void,
  opts?: {
    enabled?: boolean;
    schema?: string;
    table?: string;
    filter?: string;
  },
) {
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;

  const enabled = opts?.enabled ?? true;
  const schema = opts?.schema ?? "public";
  const table = opts?.table;
  const filter = opts?.filter;

  useEffect(() => {
    if (!enabled || !table) return;
    const supabase = createClient();
    const ch = supabase.channel(channel);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (ch as any).on(
      "postgres_changes",
      { event, schema, table, ...(filter ? { filter } : {}) },
      (payload: unknown) => {
        try { cbRef.current(payload); } catch { /* silent — a bad handler shouldn't kill the socket */ }
      },
    ).subscribe();

    return () => {
      supabase.removeChannel(ch);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel, event, schema, table, filter, enabled]);
}
