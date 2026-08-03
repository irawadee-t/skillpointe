"use client";

/**
 * Applicant Messages Inbox — client component.
 *
 * Polls /conversations every 15s to surface new unread counts without a
 * page refresh. Pauses polling when the tab is hidden so we don't burn
 * requests in the background.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MessageSquare } from "lucide-react";

import { Card, SearchInput, Stagger, StaggerItem } from "@/components/ui";
import { useRealtimeChannel } from "@/hooks/useRealtimeChannel";
import { FADE_IN_FAST, RISE_IN } from "@/lib/motion";
import { formatRelative } from "@/lib/time";

interface Conversation {
  conversation_id: string;
  other_party_name: string;
  job_title: string | null;
  last_message_at: string;
  unread_count: number;
  message_count: number;
}

// Polling now serves only as a fallback for Realtime — bumped to 60s so we
// aren't burning requests when the socket is doing the work.
const POLL_MS = 60_000;

export function MessagesInboxClient({
  token,
  initial,
}: {
  token: string;
  initial: Conversation[];
}) {
  const [conversations, setConversations] = useState<Conversation[]>(initial);
  const [search, setSearch] = useState("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Rows present at first render appear via the list's stagger reveal; rows
  // that ARRIVE later (poll/realtime refetch) rise in individually. Tracking
  // ids keeps existing rows from re-animating on refetch. (Render-time ref
  // mutation is idempotent, so double-renders are safe.)
  const knownIdsRef = useRef<Set<string>>(new Set(initial.map((c) => c.conversation_id)));
  const enteringIdsRef = useRef<Set<string>>(new Set());
  for (const c of conversations) {
    if (!knownIdsRef.current.has(c.conversation_id)) {
      knownIdsRef.current.add(c.conversation_id);
      enteringIdsRef.current.add(c.conversation_id);
    }
  }

  // Live filter — the list narrows with every letter typed (in-memory).
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter(
      (c) =>
        c.other_party_name.toLowerCase().includes(q) ||
        (c.job_title ?? "").toLowerCase().includes(q),
    );
  }, [conversations, search]);

  const refetch = useCallback(async () => {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${API_URL}/conversations`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (!res.ok) return;
      const data: Conversation[] = await res.json();
      setConversations(data);
    } catch {
      /* silent — next tick will retry */
    }
  }, [token]);

  useEffect(() => {
    // Kick off the interval; also refetch when the tab becomes visible again
    // so the inbox is fresh the moment the user returns.
    timerRef.current = setInterval(refetch, POLL_MS);
    const onVis = () => {
      if (document.visibilityState === "visible") refetch();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [refetch]);

  // Realtime: any new row on direct_messages refetches the inbox so unread
  // counts + last-message timestamps update instantly. We over-fetch on
  // purpose — filtering by recipient at the Realtime layer would require
  // a schema-aware filter string and it's cheap enough to just refetch.
  useRealtimeChannel(
    "inbox:applicant",
    "INSERT",
    () => { refetch(); pulseNav(); },
    { table: "direct_messages" },
  );

  if (conversations.length === 0) {
    return (
      <div className="bg-stone border border-transparent rounded-md p-12 text-center">
        <MessageSquare className="w-10 h-10 text-slate mx-auto mb-3" />
        <p className="text-[1.0625rem] font-medium text-cohere-ink">No messages yet</p>
        <p className="text-body text-slate mt-1">
          Employers who match with you can send you messages here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <SearchInput
        value={search}
        onChange={setSearch}
        placeholder="Search conversations…"
        className="max-w-sm"
      />
      {filtered.length === 0 ? (
        <div className="rounded-md border border-hairline bg-white p-8 text-center">
          <p className="text-body font-medium text-cohere-ink">
            No results for &ldquo;{search.trim()}&rdquo;
          </p>
          <p className="mt-1 text-caption text-slate">Try a different name or job title.</p>
        </div>
      ) : (
    <Stagger className="space-y-2.5">
      {filtered.map((c) => (
        <StaggerItem
          key={c.conversation_id}
          className={enteringIdsRef.current.has(c.conversation_id) ? RISE_IN : undefined}
        >
          <Card interactive href={`/applicant/messages/${c.conversation_id}`} className="px-5 py-4">
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-cohere-ink truncate transition-colors duration-200">
                    {c.other_party_name}
                  </p>
                  {c.unread_count > 0 && (
                    <span className={`shrink-0 inline-flex items-center justify-center w-5 h-5 rounded-full bg-cohere-blue text-white text-micro font-medium ${FADE_IN_FAST}`}>
                      {c.unread_count}
                    </span>
                  )}
                </div>
                {c.job_title && (
                  <p className="text-body text-slate mt-0.5 truncate">
                    Re: {c.job_title}
                  </p>
                )}
                <p className="text-caption text-slate mt-0.5">
                  {c.message_count} message{c.message_count !== 1 ? "s" : ""},{" "}
                  {formatRelative(c.last_message_at)}
                </p>
              </div>
              <MessageSquare className="w-4 h-4 text-slate shrink-0 ml-3" />
            </div>
          </Card>
        </StaggerItem>
      ))}
    </Stagger>
      )}
    </div>
  );
}

/**
 * Fire a global "new message" pulse. AppSidebar (or any consumer) can listen
 * for `sn:messages-arrived` on `window` and flash its Messages nav item.
 * Kept as an event so this file doesn't need to know how the sidebar renders.
 */
function pulseNav() {
  if (typeof window === "undefined") return;
  try { window.dispatchEvent(new CustomEvent("sn:messages-arrived")); }
  catch { /* silent */ }
}
