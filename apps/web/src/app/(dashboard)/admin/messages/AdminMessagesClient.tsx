"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { EmptyState, ErrorState, SkeletonRow } from "@/components/ui";
import { useAutoRevalidate } from "@/hooks/useAutoRevalidate";
import { useRealtimeChannel } from "@/hooks/useRealtimeChannel";
import { formatRelative } from "@/lib/time";

type Conversation = {
  id: string;
  counterparty_name: string;
  counterparty_email: string | null;
  counterparty_role: "applicant" | "employer";
  last_message_preview: string | null;
  last_message_at: string | null;
  unread_count: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function AdminMessagesClient({
  token,
  view,
}: {
  token: string;
  view: "applicants" | "employers";
}) {
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchConversations = async () => {
    try {
      const res = await fetch(`${API_URL}/conversations?counterparty_role=${view}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`API ${res.status}`);
      const data = (await res.json()) as Conversation[];
      setConversations(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load conversations");
    }
  };

  useEffect(() => {
    setConversations(null);
    fetchConversations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  // Auto-refresh every 60s as a fallback — Realtime handles the live case below.
  useAutoRevalidate(fetchConversations, { intervalMs: 60_000 });

  // Realtime: refetch when any direct_message row is inserted so admin sees
  // new threads / unread bumps without a poll cycle.
  useRealtimeChannel(
    `inbox:admin:${view}`,
    "INSERT",
    () => {
      fetchConversations();
      if (typeof window !== "undefined") {
        try { window.dispatchEvent(new CustomEvent("sn:messages-arrived")); } catch { /* silent */ }
      }
    },
    { table: "direct_messages" },
  );

  if (error) {
    return (
      <ErrorState
        title="Couldn't load conversations"
        message={error}
        onRetry={fetchConversations}
      />
    );
  }

  if (conversations === null) {
    return <div className="rounded-xl border border-hairline bg-white p-6"><SkeletonRow rows={5} /></div>;
  }

  if (conversations.length === 0) {
    return (
      <EmptyState
        title={view === "applicants" ? "No applicant threads yet" : "No employer threads yet"}
        body={
          view === "applicants"
            ? "Send a message from an applicant profile to start a thread."
            : "Send a message from an employer profile to start a thread."
        }
        action={{
          label: view === "applicants" ? "Open applicants" : "Open employers",
          href: view === "applicants" ? "/admin/applicants" : "/admin/employers",
        }}
      />
    );
  }

  return (
    <ul className="divide-y divide-hairline overflow-hidden rounded-xl border border-hairline bg-white">
      {conversations.map((c) => (
        <li key={c.id}>
          <Link
            href={`/admin/messages/${c.id}`}
            className="flex items-start gap-3 px-5 py-4 transition-colors hover:bg-parchment/50"
          >
            {c.unread_count > 0 && (
              <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-studio-maroon" aria-label={`${c.unread_count} unread`} />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-3">
                <p className="truncate text-[14px] font-medium text-cohere-ink">
                  {c.counterparty_name}
                </p>
                {c.last_message_at && (
                  <span className="shrink-0 text-[11px] text-slate-muted">
                    {formatRelative(c.last_message_at)}
                  </span>
                )}
              </div>
              {c.counterparty_email && (
                <p className="mt-0.5 truncate text-[12px] text-slate-muted">{c.counterparty_email}</p>
              )}
              {c.last_message_preview && (
                <p className="mt-1 truncate text-[13px] text-slate">{c.last_message_preview}</p>
              )}
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
