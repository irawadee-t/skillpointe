"use client";

import { useEffect, useState } from "react";
import { Sparkles, ShieldCheck, MessageSquare, ArrowRight, X } from "lucide-react";
import { MonoLabel } from "@/components/ui";

const KEY = "skillpointe:first-run-tour:v1";

/**
 * Three-card first-run tour, shown once per browser on the applicant dashboard.
 * Non-blocking (overlay is dismissable with a close button or backdrop click),
 * saves dismissal to localStorage so it never returns for that browser.
 */
export function FirstRunTour({ displayName }: { displayName?: string | null }) {
  const [visible, setVisible] = useState(false);
  const [i, setI] = useState(0);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const seen = localStorage.getItem(KEY);
    if (!seen) setVisible(true);
  }, []);

  if (!visible) return null;

  function dismiss() {
    localStorage.setItem(KEY, new Date().toISOString());
    setVisible(false);
  }

  const cards = [
    {
      Icon: Sparkles,
      eyebrow: "How we rank",
      title: "Every match is scored on 9 dimensions.",
      body: "Trade fit, credentials, drive-time, timing, experience, and more. We show you the score AND the reasons — no black boxes.",
    },
    {
      Icon: ShieldCheck,
      eyebrow: "How we verify",
      title: "Your credentials carry real weight.",
      body: "Add your OSHA, CDL, NCCER, or degree. We check them against the national registries so employers see a verified badge, not a claim.",
    },
    {
      Icon: MessageSquare,
      eyebrow: "How we reach you",
      title: "You choose email, text, or both.",
      body: "We only ping you when it matters — a new match, an interview time, a message. Silence is a feature.",
    },
  ];

  const current = cards[i];
  const isLast = i === cards.length - 1;

  return (
    <div className="fixed inset-0 z-[65] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Welcome tour">
      <div className="absolute inset-0 bg-studio-dark-cork/40 backdrop-blur-sm" onClick={dismiss} />

      <div className="relative w-full max-w-md overflow-hidden rounded-xl border border-hairline bg-white shadow-[0_32px_64px_-24px_rgba(12,10,9,0.32)]">
        <button
          onClick={dismiss}
          aria-label="Dismiss"
          className="absolute right-3 top-3 rounded-md p-1 text-slate-muted hover:bg-stone/60 hover:text-cohere-ink"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="p-8">
          {i === 0 && (
            <MonoLabel className="mb-2 block text-studio-maroon">
              Welcome{displayName ? `, ${displayName.split(" ")[0]}` : ""}
            </MonoLabel>
          )}
          <div className="flex items-center gap-2">
            <current.Icon className="h-5 w-5 text-cohere-green" strokeWidth={1.75} />
            <span className="mono-label text-cohere-green">{current.eyebrow}</span>
          </div>
          <h2 className="mt-3 font-display text-feature text-cohere-ink">{current.title}</h2>
          <p className="mt-3 text-body text-slate">{current.body}</p>

          {/* Dots */}
          <div className="mt-6 flex items-center gap-1.5">
            {cards.map((_, idx) => (
              <button
                key={idx}
                onClick={() => setI(idx)}
                aria-label={`Card ${idx + 1}`}
                className={`h-1.5 rounded-full transition-all ${idx === i ? "w-6 bg-studio-dark-cork" : "w-1.5 bg-stone"}`}
              />
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-hairline bg-stone/40 px-6 py-3">
          <button onClick={dismiss} className="text-caption text-slate hover:text-cohere-ink">
            Skip
          </button>
          {isLast ? (
            <button onClick={dismiss} className="btn-primary inline-flex items-center gap-1.5">
              Got it <ArrowRight className="h-4 w-4" />
            </button>
          ) : (
            <button onClick={() => setI((v) => v + 1)} className="btn-primary inline-flex items-center gap-1.5">
              Next <ArrowRight className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
