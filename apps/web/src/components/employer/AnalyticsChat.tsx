"use client";

import { useEffect, useState } from "react";
import { Send, Loader2 } from "lucide-react";

import { apiFetch } from "@/lib/api/client";
import { MonoLabel, OrbMark, ThinkingOrb } from "@/components/ui";

/**
 * Analytics chat bar — one-shot QA on top of the employer's own numbers.
 * Renders inline at the bottom of the analytics page. Example prompts help
 * new users find useful questions.
 */
interface Turn { q: string; a: string; stubbed?: boolean }

export function AnalyticsChat({ token }: { token: string }) {
  const [examples, setExamples] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<string[]>("/employer/me/analytics/chat/examples", token)
      .then(setExamples)
      .catch(() => setExamples([]));
  }, [token]);

  async function ask(q: string) {
    const question = q.trim();
    if (!question || busy) return;
    setBusy(true); setErr(null); setQuestion("");
    try {
      const r = await apiFetch<{ answer: string; stubbed: boolean }>("/employer/me/analytics/chat", token, {
        method: "POST",
        body: JSON.stringify({ question }),
      });
      setTurns((prev) => [...prev, { q: question, a: r.answer, stubbed: r.stubbed }]);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Couldn't answer just now — try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-hairline bg-white p-6 shadow-[0_1px_2px_rgba(12,10,9,0.04)]">
      <div className="flex items-center gap-2">
        <OrbMark size={18} />
        <MonoLabel className="text-cohere-green">Ask about your data</MonoLabel>
      </div>
      <h3 className="mt-2 text-card font-medium tracking-tight text-cohere-ink">Any question about your hiring numbers.</h3>

      {/* Prior turns */}
      {turns.length > 0 && (
        <ul className="mt-4 space-y-3 border-t border-hairline pt-4">
          {turns.map((t, i) => (
            <li key={i}>
              <div className="text-caption text-slate-muted">You asked</div>
              <div className="mt-0.5 text-body text-cohere-ink">{t.q}</div>
              <div className="mt-3 text-caption text-slate-muted">Answer</div>
              <div className="mt-0.5 text-body text-cohere-ink whitespace-pre-line">{t.a}</div>
              {t.stubbed && (
                <div className="mt-1 text-micro text-slate-muted">Answered without a live AI key.</div>
              )}
            </li>
          ))}
        </ul>
      )}

      {busy && (
        <div className="mt-4 flex items-center gap-2.5 text-caption text-slate-muted" role="status">
          <ThinkingOrb size={24} />
          <span>Reading your numbers…</span>
        </div>
      )}

      {err && <p className="mt-3 text-caption text-studio-maroon">{err}</p>}

      {/* Composer */}
      <form
        onSubmit={(e) => { e.preventDefault(); ask(question); }}
        className="mt-5 flex flex-col gap-2 sm:flex-row sm:items-center"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about your numbers…"
          className="input-cohere flex-1"
          disabled={busy}
        />
        <button
          type="submit"
          disabled={busy || !question.trim()}
          className="btn-primary inline-flex shrink-0 items-center gap-1.5"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          Ask
        </button>
      </form>

      {/* Example prompts */}
      {examples.length > 0 && turns.length === 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {examples.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => ask(ex)}
              disabled={busy}
              className="rounded-full border border-hairline bg-white px-3 py-1 text-caption text-slate transition-colors hover:border-cohere-ink hover:text-cohere-ink disabled:opacity-40"
            >
              {ex}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
