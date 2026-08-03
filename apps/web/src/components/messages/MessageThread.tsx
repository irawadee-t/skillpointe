"use client";

/**
 * MessageThread — polling + realtime DM thread component.
 *
 * Fetches messages on mount, then polls every 15 seconds as a fallback while
 * Supabase Realtime handles the live case. Marks the conversation as read
 * when focused. Used by both applicant and employer conversation pages.
 *
 * Motion + flow (design contract, chat surfaces):
 * - New messages rise in gently (200ms ease-out, motion-safe). Key stability
 *   is preserved across poll refetches — an optimistic send keeps its client
 *   key when the server row replaces it, so nothing ever re-animates.
 * - Sends are optimistic: the bubble appears instantly in a quiet pending
 *   state (dimmed + "Sending…"), resolves in place on ack, and on failure
 *   shows "Not delivered. Tap to retry" on the bubble itself — a real retry.
 * - Scroll is pinned-to-bottom via useStickToBottom (48px threshold): the
 *   reader is never yanked while scrolled up; a quiet "↓ New message" pill
 *   invites them back down instead. Own sends scroll smoothly (instantly
 *   under reduced motion).
 * - While loading, a shape-matched bubble skeleton holds the thread area so
 *   content streams in without a jump; header and composer render at once.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { Clock3, SendHorizonal } from "lucide-react";
import { useRealtimeChannel } from "@/hooks/useRealtimeChannel";
import { useStickToBottom } from "@/hooks/useStickToBottom";
import { NewMessagePill } from "@/components/messages/NewMessagePill";
import { API_BASE } from "@/lib/api/client";
import { RISE_IN } from "@/lib/motion";
import { useViewAs, VIEW_AS_READONLY_TOOLTIP } from "@/hooks/useViewAs";

interface ServerMessage {
  message_id: string;
  sender_role: string;
  content: string;
  created_at: string;
  is_mine: boolean;
}

interface UiMessage extends ServerMessage {
  /** Stable React key — survives the optimistic → server-row handoff. */
  clientKey: string;
  /** Absent on delivered messages. */
  status?: "pending" | "failed";
}

interface Props {
  conversationId: string;
  otherPartyName: string;
  jobTitle: string | null;
  token: string;
  myRole: "applicant" | "employer";
}

/** Composer growth cap — roughly six rows of text (matches the chat client). */
const COMPOSER_MAX_HEIGHT = 160;

export function MessageThread({
  conversationId,
  otherPartyName,
  jobTitle,
  token,
  myRole,
}: Props) {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const { isViewAs } = useViewAs();
  const [input, setInput] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  // Key + animation bookkeeping. keyMap: server message_id → client key so a
  // refetch never changes a rendered message's key. seenKeys: every key ever
  // rendered. animatedKeys: keys that should carry the entrance animation —
  // only messages that appeared AFTER the initial load.
  const keyMapRef = useRef<Map<string, string>>(new Map());
  const seenKeysRef = useRef<Set<string>>(new Set());
  const animatedKeysRef = useRef<Set<string>>(new Set());
  const initializedRef = useRef(false);
  const seqRef = useRef(0);

  const {
    containerRef,
    handleScroll,
    scrollToBottom,
    onContentAppended,
    hasUnseen,
    pinnedRef,
  } = useStickToBottom<HTMLDivElement>();

  /** Merge a server message list into local state, preserving client keys,
   *  adopting freshly-inserted own rows into their optimistic bubbles, and
   *  keeping unresolved local sends (pending/failed) at the tail. */
  const mergeServerMessages = useCallback((server: ServerMessage[]) => {
    setMessages((prev) => {
      const km = keyMapRef.current;
      const locals = prev.filter(
        (m) => m.status === "pending" || m.status === "failed",
      );
      const unclaimed = [...locals];
      const ui: UiMessage[] = server.map((m) => {
        let key = km.get(m.message_id);
        if (!key && m.is_mine) {
          // A realtime refetch can land before the POST response: adopt the
          // matching in-flight bubble so it never renders twice.
          const i = unclaimed.findIndex((l) => l.content === m.content);
          if (i >= 0) {
            key = unclaimed[i].clientKey;
            km.set(m.message_id, key);
            unclaimed.splice(i, 1);
          }
        }
        return { ...m, clientKey: key ?? m.message_id };
      });
      const serverKeys = new Set(ui.map((m) => m.clientKey));
      const kept = locals.filter((l) => !serverKeys.has(l.clientKey));
      const next = [...ui, ...kept];
      for (const m of next) {
        if (!seenKeysRef.current.has(m.clientKey)) {
          if (initializedRef.current) animatedKeysRef.current.add(m.clientKey);
          seenKeysRef.current.add(m.clientKey);
        }
      }
      return next;
    });
    initializedRef.current = true;
  }, []);

  const fetchMessages = useCallback(
    async (silent = false) => {
      try {
        const res = await fetch(
          `${API_BASE}/conversations/${conversationId}/messages`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!res.ok) return;
        const data = await res.json();
        mergeServerMessages(data.messages ?? []);
        if (!silent) setLoading(false);
      } catch {
        if (!silent) setLoading(false);
      }
    },
    [conversationId, token, mergeServerMessages],
  );

  const markRead = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/conversations/${conversationId}/read`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {}
  }, [conversationId, token]);

  // Initial load + mark read
  useEffect(() => {
    fetchMessages();
    markRead();

    // Poll as fallback — Realtime handles the live case, so 15s is plenty.
    pollRef.current = setInterval(() => fetchMessages(true), 15_000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchMessages, markRead]);

  // Realtime: any new direct_message in this conversation triggers an
  // immediate refetch so the other side's reply appears without waiting
  // on the polling tick. Also mark read so the badge clears.
  useRealtimeChannel(
    `thread:${conversationId}`,
    "INSERT",
    () => {
      fetchMessages(true);
      markRead();
      if (typeof window !== "undefined") {
        try { window.dispatchEvent(new CustomEvent("sn:messages-arrived")); } catch { /* silent */ }
      }
    },
    { table: "direct_messages", filter: `conversation_id=eq.${conversationId}` },
  );

  // Scroll discipline: instant jump to the newest message on first load,
  // then pinned-follow for growth — own sends always scroll, incoming
  // messages scroll only while the reader is pinned (pill otherwise).
  const lastCountRef = useRef(0);
  const didInitialScrollRef = useRef(false);
  const justSentRef = useRef(false);
  useEffect(() => {
    if (loading) return;
    const prevCount = lastCountRef.current;
    lastCountRef.current = messages.length;
    if (!didInitialScrollRef.current) {
      didInitialScrollRef.current = true;
      scrollToBottom({ smooth: false });
      return;
    }
    if (messages.length > prevCount) {
      const own = justSentRef.current;
      justSentRef.current = false;
      onContentAppended({ own });
    }
  }, [messages, loading, scrollToBottom, onContentAppended]);

  // iOS Safari: when the on-screen keyboard opens, visualViewport shrinks —
  // apply the delta as bottom padding so the input isn't hidden behind the
  // keyboard and the last message stays in view.
  const [kbInset, setKbInset] = useState(0);
  useEffect(() => {
    if (typeof window === "undefined" || !window.visualViewport) return;
    const vv = window.visualViewport;
    const onResize = () => {
      const delta = Math.max(0, window.innerHeight - (vv?.height ?? window.innerHeight));
      setKbInset(delta);
      // Nudge the latest message back into view once the keyboard settles —
      // but only if the reader was already at the bottom.
      if (pinnedRef.current) scrollToBottom({ smooth: true });
    };
    vv.addEventListener("resize", onResize);
    vv.addEventListener("scroll", onResize);
    return () => {
      vv.removeEventListener("resize", onResize);
      vv.removeEventListener("scroll", onResize);
    };
  }, [pinnedRef, scrollToBottom]);

  /** Grow the composer with its content, up to ~6 rows, then scroll inside. */
  function autoGrowComposer() {
    const ta = composerRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, COMPOSER_MAX_HEIGHT)}px`;
  }

  function resetComposerHeight() {
    const ta = composerRef.current;
    if (ta) ta.style.height = "auto";
  }

  /** POST one message; resolve the optimistic bubble in place on ack, or
   *  mark it failed (bubble-level retry) without losing the content. */
  const deliver = useCallback(
    async (clientKey: string, content: string) => {
      try {
        const res = await fetch(
          `${API_BASE}/conversations/${conversationId}/messages`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ content }),
          },
        );
        if (!res.ok) throw new Error("send failed");
        const real: ServerMessage = await res.json();
        keyMapRef.current.set(real.message_id, clientKey);
        setMessages((prev) =>
          prev.map((m) =>
            m.clientKey === clientKey ? { ...real, clientKey } : m,
          ),
        );
      } catch {
        // Only flip to failed if the row is still in-flight — a racing
        // realtime refetch may have already confirmed delivery.
        setMessages((prev) =>
          prev.map((m) =>
            m.clientKey === clientKey && m.status === "pending"
              ? { ...m, status: "failed" as const }
              : m,
          ),
        );
      }
    },
    [conversationId, token],
  );

  function sendMessage() {
    const text = input.trim();
    if (!text || isViewAs) return;

    const clientKey = `local-${Date.now()}-${seqRef.current++}`;
    const optimistic: UiMessage = {
      message_id: clientKey,
      clientKey,
      sender_role: myRole,
      content: text,
      created_at: new Date().toISOString(),
      is_mine: true,
      status: "pending",
    };
    seenKeysRef.current.add(clientKey);
    animatedKeysRef.current.add(clientKey);
    justSentRef.current = true;
    setMessages((prev) => [...prev, optimistic]);
    setInput("");
    resetComposerHeight();
    void deliver(clientKey, text);
  }

  function retryMessage(m: UiMessage) {
    setMessages((prev) =>
      prev.map((x) =>
        x.clientKey === m.clientKey ? { ...x, status: "pending" as const } : x,
      ),
    );
    void deliver(m.clientKey, m.content);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function sameDay(a: string, b: string): boolean {
    return new Date(a).toDateString() === new Date(b).toDateString();
  }

  function dayLabel(iso: string): string {
    const d = new Date(iso);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    if (d.toDateString() === today.toDateString()) return "Today";
    if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
    return d.toLocaleDateString([], {
      weekday: "short",
      month: "short",
      day: "numeric",
      ...(d.getFullYear() !== today.getFullYear() ? { year: "numeric" } : {}),
    });
  }

  const initial = (otherPartyName || "?").trim().charAt(0).toUpperCase();

  return (
    <div className="flex flex-col h-full">
      {/* Thread header */}
      <div className="flex items-center gap-3 border-b border-border-light pb-3 mb-4">
        <span
          aria-hidden
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-[14px] font-semibold text-white"
        >
          {initial}
        </span>
        <div className="min-w-0">
          <p className="text-[1.0625rem] font-medium text-cohere-ink truncate">{otherPartyName}</p>
          {jobTitle && (
            <p className="text-caption text-slate-muted mt-0.5 truncate">About: {jobTitle}</p>
          )}
        </div>
      </div>

      {/* Message list — content hugs the bottom (above the composer) when
          short, and scrolls normally once it overflows.

          Sender identity: my messages sit right in an ink-on-light bubble;
          the other party's sit LEFT in a white hairline bubble with a compact
          sender-name label on the first message of each group. Consecutive
          same-sender messages group with 4px gaps (contract: chat surfaces). */}
      <div className="relative min-h-0 flex-1">
        <div
          ref={containerRef}
          onScroll={handleScroll}
          className="h-full overflow-y-auto flex flex-col"
        >
          <div className="mt-auto pb-2">
            {loading ? (
              /* Shape-matched skeleton — alternating bubble bars where the
                 conversation will land, so content streams in without a jump. */
              <div
                className="space-y-3 py-2"
                role="status"
                aria-label="Loading conversation"
              >
                <span className="sr-only">Loading conversation…</span>
                <div className="h-14 w-2/3 animate-pulse rounded-md rounded-bl-sm bg-stone/70 motion-reduce:animate-none" aria-hidden />
                <div className="ml-auto h-10 w-1/2 animate-pulse rounded-md rounded-br-sm bg-stone/70 motion-reduce:animate-none" aria-hidden />
                <div className="h-16 w-3/4 animate-pulse rounded-md rounded-bl-sm bg-stone/70 motion-reduce:animate-none" aria-hidden />
                <div className="ml-auto h-10 w-2/5 animate-pulse rounded-md rounded-br-sm bg-stone/70 motion-reduce:animate-none" aria-hidden />
              </div>
            ) : (
              <div className="animate-[fade-in_150ms_ease_both]">
                {messages.length === 0 && (
                  <p className="text-caption text-slate-muted text-center py-8">
                    No messages yet. Introduce yourself.
                  </p>
                )}
                {messages.map((m, i) => {
                  const prev = messages[i - 1];
                  const next = messages[i + 1];
                  const newDay = !prev || !sameDay(prev.created_at, m.created_at);
                  const firstOfGroup = !prev || prev.is_mine !== m.is_mine || newDay;
                  // Last message of a sender group gets an ALWAYS-VISIBLE timestamp
                  // (hover doesn't exist on touch); the rest stay quiet.
                  const lastOfGroup =
                    !next || next.is_mine !== m.is_mine || !sameDay(m.created_at, next.created_at);
                  const time = new Date(m.created_at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  });
                  const entering = animatedKeysRef.current.has(m.clientKey);
                  return (
                    <div key={m.clientKey}>
                      {newDay && (
                        <div className={`flex items-center gap-3 ${i === 0 ? "" : "mt-4"} mb-2`} role="separator" aria-label={dayLabel(m.created_at)}>
                          <span className="h-px flex-1 bg-hairline" aria-hidden />
                          <span className="text-micro font-medium text-slate-muted">{dayLabel(m.created_at)}</span>
                          <span className="h-px flex-1 bg-hairline" aria-hidden />
                        </div>
                      )}
                      <div
                        className={`flex ${m.is_mine ? "justify-end" : "justify-start"} ${
                          i === 0 || newDay ? "" : firstOfGroup ? "mt-3" : "mt-1"
                        } ${entering ? RISE_IN : ""}`}
                      >
                        <div className={`max-w-[min(75%,65ch)] ${m.is_mine ? "text-right" : "text-left"}`}>
                          {!m.is_mine && firstOfGroup && (
                            <p className="mb-1 pl-1 text-micro font-medium text-slate-muted">
                              {otherPartyName}
                            </p>
                          )}
                          <div
                            className={`inline-block rounded-md px-4 py-2.5 text-left text-body leading-relaxed transition-opacity duration-200 ${
                              m.is_mine
                                ? "bg-parchment border border-hairline text-ink rounded-br-sm"
                                : "bg-white border border-hairline text-ink rounded-bl-sm"
                            } ${m.status === "pending" ? "opacity-70" : ""} ${
                              m.status === "failed" ? "cursor-pointer border-error-red/40" : ""
                            }`}
                            title={m.status ? undefined : time}
                            onClick={m.status === "failed" ? () => retryMessage(m) : undefined}
                          >
                            <p className="whitespace-pre-wrap">{m.content}</p>
                          </div>
                          {m.status === "pending" ? (
                            <p className="mt-0.5 flex items-center justify-end gap-1 pr-1 text-micro text-slate-muted">
                              <Clock3 className="h-3 w-3" aria-hidden /> Sending…
                            </p>
                          ) : m.status === "failed" ? (
                            <button
                              type="button"
                              onClick={() => retryMessage(m)}
                              className="mt-0.5 pr-1 text-micro text-error-red underline-offset-2 hover:underline"
                            >
                              Not delivered. Tap to retry
                            </button>
                          ) : (
                            lastOfGroup && (
                              <p className={`mt-0.5 text-micro text-slate-muted ${m.is_mine ? "pr-1" : "pl-1"}`}>
                                {time}
                              </p>
                            )
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
        {hasUnseen && (
          <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
            <NewMessagePill onClick={() => scrollToBottom({ smooth: true })} />
          </div>
        )}
      </div>

      {/* Input — sticky at bottom so it survives iOS keyboard opening. */}
      <div
        className="sticky bottom-0 flex items-end gap-2 border-t border-border-light bg-white pt-3 mt-2"
        style={{
          paddingBottom: `calc(env(safe-area-inset-bottom) + ${kbInset}px)`,
        }}
      >
        <textarea
          ref={composerRef}
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            autoGrowComposer();
          }}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={isViewAs}
          title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
          placeholder="Write a message… (Enter to send)"
          className="input-cohere max-h-40 min-h-[44px] flex-1 resize-none overflow-y-auto disabled:opacity-50"
        />
        <button
          onClick={sendMessage}
          disabled={!input.trim() || isViewAs}
          title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
          aria-label="Send message"
          className="shrink-0 inline-flex h-11 w-11 items-center justify-center rounded-[3px] bg-ink text-white hover:opacity-90 disabled:opacity-40 transition-opacity"
        >
          <SendHorizonal className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
