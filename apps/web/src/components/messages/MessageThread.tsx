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

    // Poll every 5s
    pollRef.current = setInterval(() => fetchMessages(true), 5000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchMessages, markRead]);

  // Scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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
      <div className="flex justify-center items-center py-16">
        <Loader2 className="w-5 h-5 animate-spin text-zinc-500" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Thread header */}
      <div className="border-b border-zinc-800 pb-3 mb-4">
        <p className="font-semibold text-white">{otherPartyName}</p>
        {jobTitle && (
          <p className="text-xs text-zinc-500 mt-0.5">Re: {jobTitle}</p>
        )}
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto space-y-3 pb-2">
        {messages.length === 0 && (
          <p className="text-sm text-zinc-500 text-center py-8">
            No messages yet. Say hello!
          </p>
        )}
        {messages.map((m) => (
          <div
            key={m.message_id}
            className={`flex ${m.is_mine ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                m.is_mine
                  ? "bg-cyan-500/20 border border-cyan-500/30 text-white rounded-br-sm"
                  : "bg-zinc-800 border border-zinc-700 text-zinc-200 rounded-bl-sm"
              }`}
            >
              <p className="whitespace-pre-wrap">{m.content}</p>
              <p
                className={`text-[10px] mt-1 ${
                  m.is_mine ? "text-white/50 text-right" : "text-zinc-500"
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

      {/* Input */}
      {error && <p className="text-xs text-rose-400 mb-1">{error}</p>}
      <div className="flex items-end gap-2 border-t border-zinc-800 pt-3 mt-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          placeholder="Write a message… (Enter to send)"
          className="flex-1 resize-none border border-zinc-700 rounded-xl px-3 py-2 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
        />
        <button
          onClick={sendMessage}
          disabled={!input.trim() || sending}
          className="shrink-0 p-2.5 bg-cyan-500 text-black rounded-xl hover:bg-cyan-400 disabled:opacity-40 transition-colors"
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
