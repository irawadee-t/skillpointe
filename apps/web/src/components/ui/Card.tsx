"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";

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
  /** Hover feedback (tone deepen / soft shadow) — for clickable / linked cards. */
  interactive?: boolean;
  href?: string;
};

const TONE_CLASS: Record<CardTone, string> = {
  white:     "bg-white border border-hairline",
  stone:     "bg-stone border border-transparent",
  parchment: "bg-parchment border border-transparent",
  ink:       "bg-ink border border-transparent text-white",
  green:     "bg-cohere-green border border-transparent text-white",
};

const ACCENT_CLASS: Record<CardAccent, string> = {
  coral: "before:bg-studio-maroon",
  green: "before:bg-cohere-green",
  blue:  "before:bg-cohere-blue",
  gold:  "before:bg-[#c9a24d]",
  ink:   "before:bg-ink",
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
    // Airbnb card: 14px radius, flat at rest, one hover elevation tier, no lift.
    "relative rounded-[14px] transition-[color,background-color,border-color,box-shadow] duration-200 ease-cohere",
    TONE_CLASS[tone],
    // Colored accent rule — a 3px top band rendered via a ::before pseudo,
    // clipped to the card's rounded corners.
    accent && cn(
      "overflow-hidden",
      "before:absolute before:left-0 before:top-0 before:h-[3px] before:w-full before:content-['']",
      ACCENT_CLASS[accent],
    ),
    interactive && tone === "white" && "hover:shadow-float",
    interactive && (tone === "stone" || tone === "parchment") && "hover:bg-parchment",
    interactive && tone === "ink" && "hover:bg-ink/95",
    interactive && tone === "green" && "hover:bg-cohere-green/95",
    className,
  );

  if (href) {
    return (
      <div>
        <Link href={href} className={cn(base, "block")}>
          {children}
        </Link>
      </div>
    );
  }

  return <div className={base}>{children}</div>;
}
