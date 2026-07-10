"use client";

/**
 * ChatClient — interactive chat interface for the applicant planning chat.
 * Renders message history and handles sending new messages to the API.
 */
import { useState, useRef, useEffect } from "react";
import { Send, Loader2 } from "lucide-react";
import { Markdown } from "@/components/ui/Markdown";
import { OrbMark, ThinkingOrb } from "@/components/ui/Orb";

interface Message {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

interface ChatClientProps {
  sessionId: string;
  initialMessages: Message[];
  isActive: boolean;
  token: string;
}

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

export function ChatClient({
  sessionId,
  initialMessages,
  isActive,
  token,
}: ChatClientProps) {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    const content = input.trim();
    if (!content || sending) return;

    setInput("");
    setSending(true);
    setError(null);

    // Optimistic user message
    const userMsg: Message = {
      message_id: `tmp-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const res = await fetch(
        `${API_URL}/applicant/me/chat/sessions/${sessionId}/messages`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ content }),
        }
      );

      if (!res.ok) throw new Error(`API error ${res.status}`);
      const assistantMsg: Message = await res.json();
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setError("Failed to send — please try again.");
      // Remove the optimistic message on failure
      setMessages((prev) => prev.filter((m) => m.message_id !== userMsg.message_id));
      setInput(content);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Messages — the conversation fills the room; a reading-width column. */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[46rem] space-y-5 px-5 py-6">
        {messages.length === 0 && (
          <div className="text-center py-10">
            <OrbMark size={44} className="mx-auto mb-3" label="SKILLED assistant" />
            <p className="text-body text-ink">Plan your next move.</p>
            <p className="mt-1 text-caption text-slate-muted">
              Ask about your matches, what&rsquo;s holding one back, or the fastest credential to close a gap.
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.message_id} message={msg} />
        ))}

        {sending && (
          <div className="flex items-center gap-2.5 text-caption text-slate-muted" role="status">
            <ThinkingOrb size={26} />
            <span>Thinking…</span>
          </div>
        )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Composer — pinned to the bottom of the room, not of a widget. */}
      <div className="border-t border-hairline bg-canvas">
        <div className="mx-auto w-full max-w-[46rem] px-5 py-3">
        {error && (
          <p className="text-micro text-error-red mb-2">{error}</p>
        )}
        {!isActive && (
          <p className="text-micro text-slate-muted mb-2">This session is closed.</p>
        )}
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!isActive || sending}
            rows={2}
            placeholder="Ask about your matches, gaps, certifications…"
            className="input-cohere flex-1 resize-none disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending || !isActive}
            className="shrink-0 p-2.5 bg-studio-dark-cork text-white rounded-sm hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
          >
            {sending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex items-start gap-2.5 ${isUser ? "justify-end" : ""}`}>
      {!isUser && <OrbMark size={28} className="mt-0.5" />}
      <div
        className={`max-w-[85%] rounded-lg px-4 py-3 text-body ${
          isUser
            ? "rounded-br-sm bg-parchment border border-hairline text-ink"
            : "bg-white border border-hairline text-ink shadow-subtle"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
        ) : (
          <Markdown content={message.content} />
        )}
      </div>
    </div>
  );
}
