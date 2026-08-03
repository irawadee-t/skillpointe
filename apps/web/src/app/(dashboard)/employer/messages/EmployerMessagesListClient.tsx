"use client";

/**
 * Employer inbox list — live type-ahead filter over conversations.
 * The list narrows with every letter typed (in-memory, no request needed).
 */
import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { MessageSquare } from "lucide-react";

import { Card, SearchInput, Stagger, StaggerItem } from "@/components/ui";
import { useAutoRevalidate } from "@/hooks/useAutoRevalidate";
import { formatDateShort } from "@/lib/format";
import { FADE_IN_FAST, RISE_IN } from "@/lib/motion";

interface Conversation {
  conversation_id: string;
  other_party_name: string;
  job_title: string | null;
  last_message_at: string;
  unread_count: number;
  message_count: number;
  last_message_preview?: string | null;
}

export function EmployerMessagesListClient({ conversations }: { conversations: Conversation[] }) {
  const [search, setSearch] = useState("");
  const router = useRouter();

  // The list is server-rendered; without this an applicant's new message only
  // appears after a manual reload. Same 60s cadence as the applicant inbox.
  useAutoRevalidate(() => router.refresh(), { intervalMs: 60_000 });

  // Rows present at first render appear via the list's stagger reveal; rows
  // that ARRIVE later (router.refresh) rise in individually. Tracking ids
  // keeps existing rows from re-animating. (Render-time ref mutation is
  // idempotent, so double-renders are safe.)
  const knownIdsRef = useRef<Set<string>>(
    new Set(conversations.map((c) => c.conversation_id)),
  );
  const enteringIdsRef = useRef<Set<string>>(new Set());
  for (const c of conversations) {
    if (!knownIdsRef.current.has(c.conversation_id)) {
      knownIdsRef.current.add(c.conversation_id);
      enteringIdsRef.current.add(c.conversation_id);
    }
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter(
      (c) =>
        c.other_party_name.toLowerCase().includes(q) ||
        (c.job_title ?? "").toLowerCase().includes(q),
    );
  }, [conversations, search]);

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
        <Stagger className="space-y-3">
          {filtered.map((c) => (
            <StaggerItem
              key={c.conversation_id}
              className={enteringIdsRef.current.has(c.conversation_id) ? RISE_IN : undefined}
            >
              <Card interactive href={`/employer/messages/${c.conversation_id}`} className="flex items-center justify-between px-5 py-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-semibold text-cohere-ink truncate">
                      {c.other_party_name}
                    </p>
                    {/* Job-context tag — this conversation is about a job. */}
                    {c.job_title && (
                      <span className="shrink-0 max-w-[16rem] truncate rounded-full border border-hairline bg-white px-2 py-0.5 text-[11px] font-medium text-slate">
                        {c.job_title}
                      </span>
                    )}
                    {c.unread_count > 0 && (
                      <span className={`shrink-0 inline-flex items-center justify-center min-w-5 h-5 px-1.5 rounded-full bg-cohere-blue text-white text-micro font-medium tabular-nums ${FADE_IN_FAST}`}>
                        {c.unread_count}
                      </span>
                    )}
                  </div>
                  {c.last_message_preview && (
                    <p className={`mt-0.5 truncate text-body transition-colors duration-200 ${c.unread_count > 0 ? "font-medium text-cohere-ink" : "text-slate"}`}>
                      {c.last_message_preview}
                    </p>
                  )}
                  <p className="text-caption text-slate-muted mt-0.5 tabular-nums">
                    {c.message_count} message{c.message_count !== 1 ? "s" : ""},{" "}
                    {formatDateShort(c.last_message_at)}
                  </p>
                </div>
                <MessageSquare className="w-4 h-4 text-slate shrink-0 ml-3" />
              </Card>
            </StaggerItem>
          ))}
        </Stagger>
      )}
    </div>
  );
}
