"use client";

/**
 * MessageThread — polling-based DM thread component.
 *
 * Fetches messages on mount, then polls every 5 seconds for new ones.
 * Marks the conversation as read when focused.
 * Used by both applicant and employer conversation pages.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { Loader2, SendHorizonal } from "lucide-react";
import { useRealtimeChannel } from "@/hooks/useRealtimeChannel";

interface Message {
  message_id: string;
  sender_role: string;
  content: string;
  created_at: string;
  is_mine: boolean;
}

interface Props {
  conversationId: string;
  otherPartyName: string;
  jobTitle: string | null;
  token: string;
  myRole: "applicant" | "employer";
}

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

export function MessageThread({
  conversationId,
  otherPartyName,
  jobTitle,
  token,
  myRole,
}: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchMessages = useCallback(async (silent = false) => {
    try {
      const res = await fetch(
        `${API_URL}/conversations/${conversationId}/messages`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) return;
      const data = await res.json();
      setMessages(data.messages ?? []);
      if (!silent) setLoading(false);
    } catch {
      if (!silent) setLoading(false);
    }
  }, [conversationId, token]);

  const markRead = useCallback(async () => {
    try {
      await fetch(`${API_URL}/conversations/${conversationId}/read`, {
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

  // Scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // iOS Safari: when the on-screen keyboard opens, visualViewport shrinks —
  // apply the delta as bottom padding so the input isn't hidden behind the
  // keyboard and the last message stays in view.
  const [kbInset, setKbInset] = useState(0);
  useEffect(() => {
    if (typeof window === "undefined" || !window.visualViewport) return;
    const vv = window.visualViewport;
    function onResize() {
      const delta = Math.max(0, window.innerHeight - (vv?.height ?? window.innerHeight));
      setKbInset(delta);
      // Nudge the latest message back into view once the keyboard settles.
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
    vv.addEventListener("resize", onResize);
    vv.addEventListener("scroll", onResize);
    return () => {
      vv.removeEventListener("resize", onResize);
      vv.removeEventListener("scroll", onResize);
    };
  }, []);

  async function sendMessage() {
    const text = input.trim();
    if (!text || sending) return;
    setSending(true);
    setError(null);

    // Optimistic update
    const optimistic: Message = {
      message_id: `opt-${Date.now()}`,
      sender_role: myRole,
      content: text,
      created_at: new Date().toISOString(),
      is_mine: true,
    };
    setMessages((prev) => [...prev, optimistic]);
    setInput("");

    try {
      const res = await fetch(
        `${API_URL}/conversations/${conversationId}/messages`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ content: text }),
        }
      );
      if (!res.ok) throw new Error("Failed");
      // Refresh to get the real message_id + timestamp
      await fetchMessages(true);
    } catch {
      setError("Failed to send. Please try again.");
      setMessages((prev) => prev.filter((m) => m.message_id !== optimistic.message_id));
      setInput(text);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center items-center py-16" role="status" aria-label="Loading conversation">
        <Loader2 className="w-5 h-5 animate-spin text-slate-muted" />
      </div>
    );
  }

  const initial = (otherPartyName || "?").trim().charAt(0).toUpperCase();

  return (
    <div className="flex flex-col h-full">
      {/* Thread header */}
      <div className="flex items-center gap-3 border-b border-border-light pb-3 mb-4">
        <span
          aria-hidden
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-studio-dark-cork text-[14px] font-semibold text-studio-cream"
        >
          {initial}
        </span>
        <div className="min-w-0">
          <p className="font-display text-feature text-cohere-ink truncate">{otherPartyName}</p>
          {jobTitle && (
            <p className="text-caption text-slate-muted mt-0.5 truncate">About: {jobTitle}</p>
          )}
        </div>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto space-y-3 pb-2">
        {messages.length === 0 && (
          <p className="text-caption text-slate-muted text-center py-8">
            No messages yet — introduce yourself.
          </p>
        )}
        {messages.map((m) => (
          <div
            key={m.message_id}
            className={`flex ${m.is_mine ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[75%] rounded-md px-4 py-2.5 text-body leading-relaxed ${
                m.is_mine
                  ? "bg-parchment border border-hairline text-ink rounded-br-sm"
                  : "bg-white border border-hairline text-ink shadow-subtle rounded-bl-sm"
              }`}
            >
              <p className="whitespace-pre-wrap">{m.content}</p>
              <p
                className={`text-micro mt-1 ${
                  m.is_mine ? "text-slate-muted text-right" : "text-slate-muted"
                }`}
              >
                {new Date(m.created_at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </p>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input — sticky at bottom so it survives iOS keyboard opening. */}
      {error && <p className="text-micro text-error-red mb-1">{error}</p>}
      <div
        className="sticky bottom-0 flex items-end gap-2 border-t border-border-light bg-canvas pt-3 mt-2"
        style={{
          paddingBottom: `calc(env(safe-area-inset-bottom) + ${kbInset}px)`,
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          placeholder="Write a message… (Enter to send)"
          className="input-cohere flex-1 resize-none"
        />
        <button
          onClick={sendMessage}
          disabled={!input.trim() || sending}
          aria-label="Send message"
          className="shrink-0 inline-flex items-center justify-center min-h-[44px] min-w-[44px] p-2.5 bg-studio-dark-cork text-white rounded-sm hover:opacity-90 disabled:opacity-40 transition-opacity"
        >
          {sending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <SendHorizonal className="w-4 h-4" />
          )}
        </button>
      </div>
    </div>
  );
}
