"use client";

import { motion } from "motion/react";
import { MapPin, CheckCircle2, Sparkles } from "lucide-react";
import { easeCohere } from "@/lib/motion";

const ROWS = [
  { name: "Maintenance Technician · Southwire", score: 94, tag: "Strong fit", strong: true },
  { name: "Industrial Electrician · GE Vernova", score: 88, tag: "Strong fit", strong: true },
  { name: "Mechatronics Tech · Ford", score: 71, tag: "Near fit", strong: false },
];

/** Dark agent-console mockup used in the hero — a ranked-match panel. */
export function HeroConsole() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 28, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.8, ease: easeCohere, delay: 0.15 }}
      className="relative overflow-hidden rounded-lg bg-studio-dark-cork p-5 shadow-2xl shadow-black/20 sm:p-7"
    >
      {/* console header */}
      <div className="flex items-center justify-between border-b border-white/10 pb-4">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-cohere-coral" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
        </div>
        <span className="text-micro tracking-mono text-white/40">
          continuous ranking
        </span>
      </div>

      {/* candidate context */}
      <div className="flex items-center justify-between py-4">
        <div>
          <p className="text-caption text-white/50">Scholar</p>
          <p className="text-body-lg text-white">J. Rivera, Electrical Program</p>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-white/10 px-2.5 py-1 text-micro text-white/70">
          <MapPin className="h-3 w-3" /> Carrollton, GA
        </span>
      </div>

      {/* ranked rows */}
      <div className="space-y-2.5">
        {ROWS.map((r, i) => (
          <motion.div
            key={r.name}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, ease: easeCohere, delay: 0.5 + i * 0.15 }}
            className="flex items-center justify-between rounded-sm border border-white/10 bg-white/[0.03] px-3.5 py-3"
          >
            <div className="flex items-center gap-3">
              <span className="text-caption tabular-nums text-white/40">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="text-caption text-white/90">{r.name}</span>
            </div>
            <div className="flex items-center gap-3">
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-micro ${
                  // On dark cork: never brand red for text — the coral branch
                  // keeps the red wash but reads in cream, like its sibling.
                  r.strong ? "bg-cohere-green/40 text-emerald-200" : "bg-cohere-coral/20 text-studio-cream"
                }`}
              >
                {r.strong && <CheckCircle2 className="h-3 w-3" />}
                {r.tag}
              </span>
              <span className="w-9 text-right text-caption tabular-nums text-white">
                {r.score}
              </span>
            </div>
          </motion.div>
        ))}
      </div>

      {/* explanation footer */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.1, duration: 0.6 }}
        className="mt-4 flex items-start gap-2 rounded-sm bg-white/[0.04] px-3.5 py-3"
      >
        <Sparkles className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-studio-cream/70" />
        <p className="text-micro leading-relaxed text-white/60">
          Top match: program alignment + geography within range. One credential gap flagged for review.
        </p>
      </motion.div>
    </motion.div>
  );
}
