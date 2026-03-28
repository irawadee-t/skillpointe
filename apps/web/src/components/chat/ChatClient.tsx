"use client";

/**
 * ChatClient — interactive chat interface for the applicant planning chat.
 * Renders message history and handles sending new messages to the API.
 */
import { useState, useRef, useEffect } from "react";
import { Send, Loader2, Bot, User } from "lucide-react";

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
    <div className="flex flex-col bg-white border border-zinc-200 rounded-lg overflow-hidden" style={{ minHeight: "500px" }}>
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4" style={{ maxHeight: "60vh" }}>
        {messages.length === 0 && (
          <div className="text-center py-8">
            <Bot className="w-8 h-8 text-zinc-400 mx-auto mb-2" />
            <p className="text-sm text-zinc-400">
              Ask me anything about your matches, gaps, or next steps!
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.message_id} message={msg} />
        ))}

        {sending && (
          <div className="flex items-center gap-2 text-sm text-zinc-400">
            <Bot className="w-4 h-4 text-spf-navy" />
            <Loader2 className="w-3.5 h-3.5 animate-spin text-spf-navy" />
            <span>Thinking…</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-zinc-200 p-3">
        {error && (
          <p className="text-xs text-rose-600 mb-2">{error}</p>
        )}
        {!isActive && (
          <p className="text-xs text-zinc-400 mb-2">This session is closed.</p>
        )}
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!isActive || sending}
            rows={2}
            placeholder="Ask about your matches, gaps, certifications… (Enter to send)"
            className="flex-1 border border-zinc-200 rounded-lg px-3 py-2 text-sm bg-white text-zinc-900 placeholder:text-zinc-400 resize-none focus:outline-none focus:ring-1 focus:ring-spf-navy/20 focus:border-spf-navy disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending || !isActive}
            className="shrink-0 p-2 bg-zinc-900 text-white rounded-lg hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
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
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex items-start gap-2 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${
          isUser ? "bg-zinc-900" : "bg-zinc-100"
        }`}
      >
        {isUser ? (
          <User className="w-3.5 h-3.5 text-white" />
        ) : (
          <Bot className="w-3.5 h-3.5 text-spf-navy" />
        )}
      </div>
      <div
        className={`max-w-[80%] rounded-xl px-3.5 py-2.5 text-sm ${
          isUser
            ? "bg-spf-navy/10 border border-spf-navy/20 text-zinc-900"
            : "bg-zinc-100 border border-zinc-200 text-zinc-700"
        }`}
      >
        <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
      </div>
    </div>
  );
}
