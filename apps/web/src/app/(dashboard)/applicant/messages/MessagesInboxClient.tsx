"use client";

/**
 * Applicant Messages Inbox — client component.
 *
 * Polls /conversations every 15s to surface new unread counts without a
 * page refresh. Pauses polling when the tab is hidden so we don't burn
 * requests in the background.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { MessageSquare } from "lucide-react";

import { Card, Stagger, StaggerItem } from "@/components/ui";
import { useRealtimeChannel } from "@/hooks/useRealtimeChannel";

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
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
        <p className="font-display text-feature text-cohere-ink">No messages yet</p>
        <p className="text-body text-slate mt-1">
          Employers who match with you can send you messages here.
        </p>
      </div>
    );
  }

  return (
    <Stagger className="space-y-2.5">
      {conversations.map((c) => (
        <StaggerItem key={c.conversation_id}>
          <Card interactive href={`/applicant/messages/${c.conversation_id}`} className="px-5 py-4">
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-cohere-ink truncate">
                    {c.other_party_name}
                  </p>
                  {c.unread_count > 0 && (
                    <span className="shrink-0 inline-flex items-center justify-center w-5 h-5 rounded-full bg-cohere-green text-white text-micro font-bold">
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

/** Local relative-time — kept here to avoid a cross-file import in a client leaf. */
function formatRelative(iso: string): string {
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "";
  const diffMs = Date.now() - t;
  const past = diffMs >= 0;
  const abs = Math.abs(diffMs);
  const min = Math.floor(abs / 60_000);
  if (min < 1) return past ? "just now" : "in a moment";
  if (min < 60) return past ? `${min}m ago` : `in ${min}m`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return past ? `${hr}h ago` : `in ${hr}h`;
  const d = Math.floor(hr / 24);
  if (d < 7) return past ? `${d}d ago` : `in ${d}d`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
