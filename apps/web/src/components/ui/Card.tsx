"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { easeCohere } from "@/lib/motion";

type CardTone = "white" | "stone" | "parchment" | "ink" | "green";
type CardAccent = "coral" | "green" | "blue" | "gold" | "ink";

type CardProps = {
  children: React.ReactNode;
  className?: string;
  /**
   * Surface tone.
   *   • white      — default: white with hairline border and soft edge-shadow (pops on warm canvas)
   *   • stone      — warm neutral cream, borderless (secondary/supporting content)
   *   • parchment  — slightly deeper warm neutral, for muted grouping bands
   *   • ink        — near-black dark surface (product-band moments)
   *   • green      — deep-green feature surface (hero KPI, celebration)
   */
  tone?: CardTone;
  /**
   * Optional 3-px colored top rule — signals category (coral/green/blue/gold)
   * without tinting the whole card. Great for taxonomy: match cards, job cards,
   * industry bands, etc.
   */
  accent?: CardAccent;
  /** Lift on hover — for clickable / linked cards. */
  interactive?: boolean;
  href?: string;
};

const TONE_CLASS: Record<CardTone, string> = {
  white:     "bg-white border border-hairline shadow-[0_1px_2px_rgba(12,10,9,0.04)]",
  stone:     "bg-stone border border-transparent",
  parchment: "bg-parchment border border-transparent",
  ink:       "bg-studio-dark-cork border border-transparent text-white",
  green:     "bg-cohere-green border border-transparent text-white",
};

const ACCENT_CLASS: Record<CardAccent, string> = {
  coral: "before:bg-studio-maroon",
  green: "before:bg-cohere-green",
  blue:  "before:bg-cohere-blue",
  gold:  "before:bg-[#c9a24d]",
  ink:   "before:bg-studio-dark-cork",
};

/**
 * Editorial card. Flat, hairline-defined, with an optional colored top rule
 * for category signaling. Never falls into semi-transparent tinted washes.
 */
export function Card({
  children,
  className,
  tone = "white",
  accent,
  interactive = false,
  href,
}: CardProps) {
  const base = cn(
    "relative rounded-xl transition-shadow duration-300",
    TONE_CLASS[tone],
    // Colored accent rule — a 3px top band rendered via a ::before pseudo,
    // clipped to the card's rounded corners.
    accent && cn(
      "overflow-hidden",
      "before:absolute before:left-0 before:top-0 before:h-[3px] before:w-full before:content-['']",
      ACCENT_CLASS[accent],
    ),
    interactive && tone === "white" && "hover:shadow-[0_8px_28px_-12px_rgba(12,10,9,0.12)]",
    interactive && (tone === "stone" || tone === "parchment") && "hover:bg-parchment",
    interactive && tone === "ink" && "hover:bg-studio-dark-cork/95",
    interactive && tone === "green" && "hover:bg-cohere-green/95",
    className,
  );

  if (href) {
    return (
      <motion.div
        whileHover={interactive ? { y: -4 } : undefined}
        transition={{ duration: 0.3, ease: easeCohere }}
      >
        <Link href={href} className={cn(base, "block")}>
          {children}
        </Link>
      </motion.div>
    );
  }

  return (
    <motion.div
      className={base}
      whileHover={interactive ? { y: -4 } : undefined}
      transition={{ duration: 0.3, ease: easeCohere }}
    >
      {children}
    </motion.div>
  );
}
