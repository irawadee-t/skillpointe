"use client";

/**
 * ChatClient — interactive chat interface for the applicant planning chat.
 *
 * Scaffolded on purpose: the server sends deterministic, context-aware
 * suggested questions (rendered as one-tap chips) so a first-time user never
 * faces a blank input, and every reply is followed by fresh chips until the
 * user finds their own voice. An AI-disclosure line sits under the composer.
 *
 * Delivery is progressive: replies arrive over SSE from the /messages/stream
 * endpoint (the server runs the FULL guardrail pipeline before the first byte
 * — buffer-then-stream), filling the bubble chunk by chunk with a ThinkingOrb
 * until the first chunk lands. If the stream can't start, we fall back to the
 * plain JSON endpoint so nothing is lost.
 */
import { useState, useRef, useEffect } from "react";
import { Send, Loader2, RotateCcw } from "lucide-react";
import { Markdown } from "@/components/ui/Markdown";
import { OrbMark, ThinkingOrb } from "@/components/ui/Orb";
import { NewMessagePill } from "@/components/messages/NewMessagePill";
import { useStickToBottom } from "@/hooks/useStickToBottom";
import { postSse, StreamStartError } from "@/lib/api/sse";
import { RISE_IN } from "@/lib/motion";
import { formatTime } from "@/lib/time";

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
  suggestedQuestions?: string[];
}

import { useViewAs, VIEW_AS_READONLY_TOOLTIP } from "@/hooks/useViewAs";

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

/** Composer growth cap — roughly six rows of text. */
const COMPOSER_MAX_HEIGHT = 160;

export function ChatClient({
  sessionId,
  initialMessages,
  isActive,
  token,
  suggestedQuestions = [],
}: ChatClientProps) {
  const { isViewAs } = useViewAs();
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  // Progressive reply text while an SSE stream is in flight; null = idle.
  const [streamText, setStreamText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastFailed, setLastFailed] = useState<string | null>(null);
  // Chips the user has already used — don't re-offer them.
  const [usedChips, setUsedChips] = useState<Set<string>>(new Set());
  const composerRef = useRef<HTMLTextAreaElement>(null);

  // Messages present at mount render statically (no entrance circus on
  // thread open); anything appended later rises in. A reply that streamed
  // into view is added here before it lands in `messages`, so the swap from
  // streaming bubble to stored message never re-animates.
  const preSeenIdsRef = useRef<Set<string>>(
    new Set(initialMessages.map((m) => m.message_id)),
  );

  // Pinned-to-bottom scroll (shared 48px-threshold pattern): the reader is
  // never yanked while scrolled up — a quiet pill invites them back down.
  const {
    containerRef,
    handleScroll,
    scrollToBottom,
    onContentAppended,
    hasUnseen,
  } = useStickToBottom<HTMLDivElement>();

  const lastCountRef = useRef(initialMessages.length);
  const didInitialScrollRef = useRef(false);
  const justSentRef = useRef(false);

  useEffect(() => {
    if (!didInitialScrollRef.current) {
      // Thread open: land on the newest message instantly — no scroll cinema.
      didInitialScrollRef.current = true;
      scrollToBottom({ smooth: false });
      return;
    }
    const prevCount = lastCountRef.current;
    lastCountRef.current = messages.length;
    if (messages.length > prevCount) {
      const own = justSentRef.current;
      justSentRef.current = false;
      onContentAppended({ own });
    }
  }, [messages, scrollToBottom, onContentAppended]);

  // Streaming growth: follow while pinned (instant, so smooth-scrolls never
  // fight the chunk cadence); pill otherwise. The thinking indicator commits
  // in the same batch as the optimistic send, so the messages effect above
  // already scrolls it into view.
  useEffect(() => {
    if (streamText === null) return;
    onContentAppended({ own: false, smooth: false });
  }, [streamText, onContentAppended]);

  const remainingChips = suggestedQuestions.filter((q) => !usedChips.has(q));
  // Show chips whenever the user isn't mid-send and the conversation is young
  // (< 6 of their own messages) — enough scaffolding without nagging forever.
  const userTurns = messages.filter((m) => m.role === "user").length;
  const showChips = isActive && !sending && remainingChips.length > 0 && userTurns < 6;

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

  /** Consume the SSE stream; resolves with the final stored message (or the
   *  accumulated partial if the stream broke after delivery began) plus
   *  whether any of it already streamed into view. */
  async function sendViaStream(
    content: string,
  ): Promise<{ msg: Message; streamed: boolean }> {
    let acc = "";
    let finalMsg: Message | null = null;

    await postSse(
      `${API_URL}/applicant/me/chat/sessions/${sessionId}/messages/stream`,
      { token, body: { content } },
      (ev) => {
        if (ev.event === "chunk" && typeof ev.data.delta === "string") {
          acc += ev.data.delta;
          setStreamText(acc);
        } else if (ev.event === "done") {
          finalMsg = ev.data as unknown as Message;
        }
      }
    );

    if (finalMsg) return { msg: finalMsg, streamed: acc.length > 0 };
    if (acc) {
      // Partial delivery: the server stored the full reply; show what we got.
      return {
        msg: {
          message_id: `stream-${Date.now()}`,
          role: "assistant",
          content: acc,
          created_at: new Date().toISOString(),
        },
        streamed: true,
      };
    }
    throw new Error("Empty stream");
  }

  /** Legacy JSON path — used only when the stream couldn't start. */
  async function sendViaJson(content: string): Promise<Message> {
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
    return res.json();
  }

  async function send(content: string) {
    if (!content || sending) return;

    setInput("");
    resetComposerHeight();
    setSending(true);
    setError(null);
    setLastFailed(null);

    // Optimistic user message
    const userMsg: Message = {
      message_id: `tmp-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    justSentRef.current = true;
    setMessages((prev) => [...prev, userMsg]);

    try {
      let assistantMsg: Message;
      try {
        const res = await sendViaStream(content);
        assistantMsg = res.msg;
        // Already on screen via the streaming bubble — swapping in the stored
        // message must not re-animate it.
        if (res.streamed) preSeenIdsRef.current.add(assistantMsg.message_id);
      } catch (err) {
        if (err instanceof StreamStartError) {
          // Graceful fallback — stream never started, JSON path is safe.
          assistantMsg = await sendViaJson(content);
        } else {
          throw err;
        }
      }
      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setError("That didn't send.");
      setLastFailed(content);
      // Remove the optimistic message on failure
      setMessages((prev) => prev.filter((m) => m.message_id !== userMsg.message_id));
    } finally {
      setSending(false);
      setStreamText(null);
    }
  }

  function handleSend() {
    void send(input.trim());
  }

  function handleChip(question: string) {
    setUsedChips((prev) => new Set(prev).add(question));
    void send(question);
  }

  function handleRetry() {
    if (lastFailed) void send(lastFailed);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Messages — the conversation fills the room; a reading-width column.
          Content hugs the bottom when short, scrolls normally when it overflows. */}
      <div className="relative min-h-0 flex-1">
        <div
          ref={containerRef}
          onScroll={handleScroll}
          className="h-full overflow-y-auto flex flex-col"
        >
          <div className="mx-auto mt-auto w-full max-w-[46rem] space-y-5 px-5 py-6">
          {messages.length === 0 && (
            <div className="text-center py-10">
              <OrbMark size={44} className="mx-auto mb-3" label="SKILLED assistant" />
              <p className="text-body text-ink">Plan your next move.</p>
              <p className="mt-1 text-caption text-slate-muted">
                Ask about your matches, what&rsquo;s holding one back, or the fastest credential to close a gap.
              </p>
            </div>
          )}

          {groupMessages(messages).map((group) => (
            <MessageGroup
              key={group[0].message_id}
              group={group}
              isNew={(id) => !preSeenIdsRef.current.has(id)}
            />
          ))}

          {/* Progressive reply — fills as validated chunks arrive. */}
          {streamText !== null && streamText.length > 0 && (
            <div className={`flex items-start gap-2.5 ${RISE_IN}`}>
              <OrbMark size={28} className="mt-0.5 shrink-0" />
              <div className="flex min-w-0 max-w-[85%] flex-col gap-1 items-start">
                <div className="max-w-[65ch] rounded-lg border border-hairline bg-white px-4 py-2.5 text-body text-ink shadow-subtle">
                  <Markdown content={streamText} />
                </div>
              </div>
            </div>
          )}

          {sending && !streamText && (
            <div className={`flex items-center gap-2.5 text-caption text-slate-muted ${RISE_IN}`} role="status">
              <ThinkingOrb size={26} />
              <span>Thinking…</span>
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

      {/* Composer — pinned to the bottom of the room, not of a widget. */}
      <div className="border-t border-hairline bg-canvas">
        <div className="mx-auto w-full max-w-[46rem] px-5 py-3">
        {/* Suggested questions — one-tap scaffolding so nobody faces a blank box. */}
        {showChips && (
          <div className="mb-2.5 flex flex-wrap gap-1.5" aria-label="Suggested questions">
            {remainingChips.slice(0, 4).map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => handleChip(q)}
                className="rounded-full border border-hairline bg-white px-3 py-1.5 text-caption text-ink transition-colors hover:border-cohere-ink hover:text-cohere-ink"
              >
                {q}
              </button>
            ))}
          </div>
        )}
        {error && (
          <p className="text-micro text-error-red mb-2 flex items-center gap-2">
            {error}
            {lastFailed && (
              <button
                type="button"
                onClick={handleRetry}
                className="inline-flex items-center gap-1 underline hover:no-underline"
              >
                <RotateCcw className="h-3 w-3" /> Try again
              </button>
            )}
          </p>
        )}
        {!isActive && (
          <p className="text-micro text-slate-muted mb-2">This session is closed.</p>
        )}
        <div className="flex gap-2 items-end">
          <textarea
            ref={composerRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              autoGrowComposer();
            }}
            onKeyDown={handleKeyDown}
            title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
            disabled={!isActive || sending || isViewAs}
            rows={1}
            placeholder="Ask about your matches, gaps, certifications…"
            className="input-cohere max-h-40 min-h-[44px] flex-1 resize-none overflow-y-auto disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending || !isActive || isViewAs}
            aria-label="Send message"
            title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-ink text-white hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
          >
            {sending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
          </div>
          <p className="mt-2 text-micro text-slate-muted">
            AI advice from your match data. Double-check important details. SKILLED never guarantees hiring outcomes.
          </p>
        </div>
      </div>
    </div>
  );
}

/** Consecutive same-role messages render as one group: 4px internal gaps,
 *  avatar only on the first message of an assistant group. */
function groupMessages(messages: Message[]): Message[][] {
  const groups: Message[][] = [];
  for (const m of messages) {
    const last = groups[groups.length - 1];
    if (last && last[0].role === m.role) last.push(m);
    else groups.push([m]);
  }
  return groups;
}

function MessageGroup({
  group,
  isNew,
}: {
  group: Message[];
  isNew: (id: string) => boolean;
}) {
  const isUser = group[0].role === "user";

  return (
    <div className={`flex items-start gap-2.5 ${isUser ? "justify-end" : ""}`}>
      {!isUser && <OrbMark size={28} className="mt-0.5 shrink-0" />}
      <div className={`flex min-w-0 max-w-[85%] flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
        {group.map((msg) => (
          <MessageBubble key={msg.message_id} message={msg} entering={isNew(msg.message_id)} />
        ))}
      </div>
    </div>
  );
}

function MessageBubble({ message, entering }: { message: Message; entering?: boolean }) {
  const isUser = message.role === "user";
  const time = formatTime(message.created_at);

  return (
    <div className={`group/msg flex w-full items-end gap-2 ${isUser ? "justify-end" : ""} ${entering ? RISE_IN : ""}`}>
      {/* Timestamp — hover only, no layout shift. Sits on the empty side of the bubble. */}
      {isUser && time && <TimeLabel time={time} />}
      <div
        className={`max-w-[65ch] rounded-lg px-4 py-2.5 text-body ${
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
      {!isUser && time && <TimeLabel time={time} />}
    </div>
  );
}

function TimeLabel({ time }: { time: string }) {
  return (
    <span
      aria-hidden
      className="mb-1 shrink-0 select-none whitespace-nowrap text-micro text-slate-muted opacity-0 transition-opacity duration-150 group-hover/msg:opacity-100"
    >
      {time}
    </span>
  );
}
