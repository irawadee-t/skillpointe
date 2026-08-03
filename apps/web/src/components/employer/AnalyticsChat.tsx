"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Loader2 } from "lucide-react";

import { apiFetch, API_BASE } from "@/lib/api/client";
import { postSse, StreamStartError } from "@/lib/api/sse";
import { NewMessagePill } from "@/components/messages/NewMessagePill";
import { OrbMark, ThinkingOrb } from "@/components/ui";
import { useStickToBottom } from "@/hooks/useStickToBottom";
import { RISE_IN } from "@/lib/motion";
import { formatTime } from "@/lib/time";

/**
 * Analytics chat — QA on top of the employer's own numbers.
 *
 * A real chat surface: a fixed-height scrollable thread (newest pinned into
 * view) with the composer anchored below it — the page never grows longer as
 * the conversation does. Bubbles match the applicant planning chat so the two
 * assistants read as one product.
 *
 * Delivery is progressive: answers arrive over SSE from /chat/stream (the
 * server computes the FULL grounded answer first — buffer-then-stream), with
 * a ThinkingOrb + quiet status line holding the assistant position until the
 * first chunk lands, replaced in place by the filling bubble. If the stream
 * can't start, we fall back to the plain JSON endpoint so nothing is lost.
 *
 * Suggested questions never vanish: once a conversation starts they collapse
 * into a compact single row above the composer and persist for the whole
 * session, with already-asked ones visually quieted. A ref guard (not just
 * state) makes asking re-entry-proof — a double-click fires exactly one turn.
 */
interface Turn {
  q: string;
  a: string;
  stubbed?: boolean;
  at: string;
}

const USER_BUBBLE =
  "max-w-[min(65ch,85%)] rounded-lg rounded-br-sm border border-hairline bg-parchment px-4 py-2.5 text-body text-cohere-ink";
const ASSISTANT_BUBBLE =
  "max-w-[min(65ch,85%)] rounded-lg border border-hairline bg-white px-4 py-2.5 text-body text-cohere-ink shadow-subtle";

export function AnalyticsChat({ token }: { token: string }) {
  const [examples, setExamples] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  // The question currently being answered — rendered as an optimistic user
  // bubble with the assistant position beneath it (thinking → streaming).
  const [pendingQ, setPendingQ] = useState<string | null>(null);
  // Progressive answer text while the SSE stream is in flight; null = idle.
  const [streamText, setStreamText] = useState<string | null>(null);
  // Questions already asked this session — their chips render quieted.
  const [asked, setAsked] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);

  // Re-entry guard. `busy` state alone races: a second click in the same
  // frame reads the stale closure value before React flushes the state
  // update, firing a duplicate request. The ref flips synchronously.
  const busyRef = useRef(false);

  // Pinned-to-bottom scroll (shared 48px-threshold pattern): auto-scroll
  // follows the stream only while the reader is at the bottom — scrolling up
  // to reread an earlier answer is respected, never yanked; a quiet pill
  // invites them back down instead.
  const {
    containerRef,
    handleScroll,
    scrollToBottom,
    onContentAppended,
    hasUnseen,
    pinnedRef,
  } = useStickToBottom<HTMLDivElement>();

  useEffect(() => {
    apiFetch<string[]>("/employer/me/analytics/chat/examples", token)
      .then(setExamples)
      .catch(() => setExamples([]));
  }, [token]);

  useEffect(() => {
    if (turns.length === 0 && pendingQ === null && streamText === null) return;
    onContentAppended({ own: false, smooth: false });
  }, [turns, pendingQ, streamText, onContentAppended]);

  /** Consume the SSE stream; resolves with the final answer (or the
   *  accumulated partial if the stream broke after delivery began). */
  async function askViaStream(q: string): Promise<{ answer: string; stubbed?: boolean }> {
    let acc = "";
    let final: { answer: string; stubbed?: boolean } | null = null;

    await postSse(
      `${API_BASE}/employer/me/analytics/chat/stream`,
      { token, body: { question: q } },
      (ev) => {
        if (ev.event === "chunk" && typeof ev.data.delta === "string") {
          acc += ev.data.delta;
          setStreamText(acc);
        } else if (ev.event === "done" && typeof ev.data.answer === "string") {
          final = ev.data as unknown as { answer: string; stubbed?: boolean };
        }
      },
    );

    if (final) return final;
    if (acc) return { answer: acc }; // partial delivery — keep what arrived
    throw new Error("Empty stream");
  }

  async function ask(raw: string) {
    const q = raw.trim();
    if (!q || busyRef.current) return;
    busyRef.current = true;

    setBusy(true);
    setErr(null);
    setQuestion("");
    setPendingQ(q);
    setStreamText(null);
    pinnedRef.current = true; // a fresh question re-pins the thread

    try {
      let result: { answer: string; stubbed?: boolean };
      try {
        result = await askViaStream(q);
      } catch (e) {
        if (e instanceof StreamStartError) {
          // Graceful fallback — the stream never started, JSON path is safe.
          result = await apiFetch<{ answer: string; stubbed: boolean }>(
            "/employer/me/analytics/chat",
            token,
            { method: "POST", body: JSON.stringify({ question: q }) },
          );
        } else {
          throw e;
        }
      }
      setTurns((prev) => [
        ...prev,
        { q, a: result.answer, stubbed: result.stubbed, at: new Date().toISOString() },
      ]);
      setAsked((prev) => new Set(prev).add(q));
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Couldn't answer just now. Try again in a moment.");
      setQuestion(q); // put the question back so retrying is one click away
    } finally {
      busyRef.current = false;
      setBusy(false);
      setPendingQ(null);
      setStreamText(null);
    }
  }

  const hasConversation = turns.length > 0 || pendingQ !== null;

  return (
    <section className="overflow-hidden rounded-[10px] border border-hairline bg-white">
      <div className="flex items-center gap-2.5 border-b border-hairline px-5 py-3.5">
        <OrbMark size={20} />
        <div>
          <h3 className="text-body font-medium text-cohere-ink">Ask about your numbers</h3>
          <p className="text-micro text-slate-muted">Answers come from your own hiring data.</p>
        </div>
      </div>

      {/* Thread — fixed height, scrolls internally; the page never elongates. */}
      <div className="relative">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="h-[22rem] overflow-y-auto bg-parchment/40 px-5 py-4"
      >
        {!hasConversation && (
          <p className="py-8 text-center text-caption text-slate-muted">
            Ask anything about your jobs, candidates, or hires.
          </p>
        )}
        <div className="space-y-4">
          {turns.map((t, i) => (
            <TurnBlock key={i} turn={t} />
          ))}

          {/* In-flight turn: optimistic question bubble, then the assistant
              position — ThinkingOrb + status line until the first chunk, the
              filling bubble after. Same slot, no layout jump. */}
          {pendingQ && (
            <div className={`space-y-2.5 ${RISE_IN}`}>
              <div className="flex justify-end">
                <div className={USER_BUBBLE}>{pendingQ}</div>
              </div>
              <div className="flex items-start gap-2.5">
                {streamText ? (
                  <OrbMark size={24} className="mt-0.5" />
                ) : (
                  <ThinkingOrb size={24} className="mt-0.5" />
                )}
                {streamText ? (
                  <div className={ASSISTANT_BUBBLE}>
                    <span className="whitespace-pre-line">{streamText}</span>
                  </div>
                ) : (
                  <p role="status" className="py-2 text-caption text-slate-muted">
                    Reading your numbers…
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      {hasUnseen && (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
          <NewMessagePill
            label="New answer"
            onClick={() => scrollToBottom({ smooth: true })}
          />
        </div>
      )}
      </div>

      {/* Composer + suggested questions — pinned under the thread. */}
      <div className="border-t border-hairline px-5 py-3.5">
        {err && <p className="mb-2 text-caption text-studio-maroon">{err}</p>}
        {examples.length > 0 && (
          <div
            key={hasConversation ? "compact" : "stacked"}
            aria-label="Suggested questions"
            className={`mb-2.5 flex gap-1.5 animate-[fade-in_150ms_ease_both] ${
              hasConversation ? "flex-nowrap overflow-x-auto pb-0.5" : "flex-wrap"
            }`}
          >
            {examples.map((ex) => {
              const wasAsked = asked.has(ex);
              return (
                <button
                  key={ex}
                  type="button"
                  onClick={() => ask(ex)}
                  aria-disabled={busy}
                  className={`shrink-0 rounded-full border border-hairline bg-white px-3 py-1.5 text-caption transition-colors duration-200 ${
                    busy
                      ? "cursor-default opacity-40"
                      : wasAsked
                        ? "text-slate-muted hover:border-cohere-ink hover:text-cohere-ink"
                        : "text-ink hover:border-cohere-ink hover:text-cohere-ink"
                  }`}
                >
                  {ex}
                </button>
              );
            })}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void ask(question);
          }}
          className="flex items-center gap-2"
        >
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question about your numbers…"
            className="input-cohere h-11 flex-1 transition-opacity duration-200 disabled:opacity-50"
            disabled={busy}
          />
          <button
            type="submit"
            disabled={busy || !question.trim()}
            aria-label="Ask"
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-ink text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </form>
      </div>
    </section>
  );
}

/** One completed question → answer exchange. Timestamps appear on hover only
 *  (per the design contract), on the empty side of each bubble. */
function TurnBlock({ turn }: { turn: Turn }) {
  const time = formatTime(turn.at);
  return (
    <div className="space-y-2.5">
      <div className="group/msg flex items-end justify-end gap-2">
        {time && <TimeLabel time={time} />}
        <div className={USER_BUBBLE}>{turn.q}</div>
      </div>
      <div className="group/msg flex items-start gap-2.5">
        <OrbMark size={24} className="mt-0.5" />
        <div className={ASSISTANT_BUBBLE}>
          <span className="whitespace-pre-line">{turn.a}</span>
          {turn.stubbed && (
            <span className="mt-1.5 block text-micro text-slate-muted">
              Calculated directly from your data.
            </span>
          )}
        </div>
        {time && <TimeLabel time={time} />}
      </div>
    </div>
  );
}

function TimeLabel({ time }: { time: string }) {
  return (
    <span
      aria-hidden
      className="mb-1 shrink-0 select-none self-end whitespace-nowrap text-micro text-slate-muted opacity-0 transition-opacity duration-150 group-hover/msg:opacity-100"
    >
      {time}
    </span>
  );
}
