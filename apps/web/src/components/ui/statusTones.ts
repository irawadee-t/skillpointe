/**
 * statusTones.ts — the ONE semantic color system for status/label chips.
 *
 * Rule (DESIGN_CONTRACT.md, "Status & chip color semantics"):
 *   one visual dimension = one meaning. Hue encodes the semantic slot;
 *   fill weight (tint → outline → solid) encodes intensity WITHIN a slot.
 *   The same entity renders identically everywhere. Verification/level is
 *   an affix (icon + micro-label), never a recolor of the entity's name.
 *
 * Fill rule (DESIGN_CONTRACT.md): status chips are SOLID DARK fills with
 * white text — never a light tint with darker same-hue text (the
 * "highlighter" pattern is banned). Intensity within a slot is encoded as
 * outline (white bg, colored border/text) → solid dark. Neutral/muted stay
 * quiet grays. Every solid pairs white text at ≥4.5:1 (AA):
 *   cohere-blue #1863dc 5.4:1 · cohere-navy #071829 17+:1 ·
 *   cohere-green #4a4b2f 9.0:1 · cohere-green-deep #31321f 12+:1 ·
 *   studio-maroon #9E1B32 7.9:1 · error-red #b30000 7.2:1.
 *
 * Slots:
 *   neutral         informational metadata, categories, self-reported (quiet outline)
 *   progress        in-flight process states (solid action blue)
 *   progressSolid   actively engaged process states (solid deep navy)
 *   positive        good / approved / verified (solid dark green)
 *   positiveOutline positive, pending acceptance (green outline)
 *   positiveSolid   strong terminal positive (solid deepest green)
 *   attention       needs action now (solid maroon — sparingly)
 *   danger          failed / error only (solid error red)
 *   muted           terminal / inactive / closed (quiet gray)
 */

import type { ApplicationStatus } from "@/components/applications/stages";

export type StatusTone =
  | "neutral"
  | "progress"
  | "progressSolid"
  | "positive"
  | "positiveOutline"
  | "positiveSolid"
  | "attention"
  | "danger"
  | "muted";

export const STATUS_TONE_CLASSES: Record<StatusTone, string> = {
  neutral: "border-hairline bg-white text-slate",
  progress: "border-cohere-blue bg-cohere-blue text-white",
  progressSolid: "border-cohere-navy bg-cohere-navy text-white",
  positive: "border-cohere-green bg-cohere-green text-white",
  positiveOutline: "border-cohere-green/50 bg-white text-cohere-green",
  positiveSolid: "border-cohere-green-deep bg-cohere-green-deep text-white",
  attention: "border-studio-maroon bg-studio-maroon text-white",
  danger: "border-error-red bg-error-red text-white",
  muted: "border-hairline bg-stone/40 text-slate-muted",
};

/**
 * The ONE attention hue for non-chip attention accents (icons, inline labels,
 * near-fit rails). Matches the `attention` chip slot — never cohere-coral.
 */
export const ATTENTION_TEXT_CLASS = "text-studio-maroon";

/** Canonical chip shell per the contract's chip rule (11px, sentence case). */
export const STATUS_CHIP_BASE =
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium";

/** Full class string for a semantic status chip. */
export function statusChipClass(tone: StatusTone, extra?: string): string {
  return `${STATUS_CHIP_BASE} ${STATUS_TONE_CLASSES[tone]}${extra ? ` ${extra}` : ""}`;
}

/* ── Domain: application stages ─────────────────────────────────────────
 * The stage ramp — identical on employer AND applicant views:
 *   New/Submitted (attention) → In review (progress tint) →
 *   Shortlisted (positive tint) → Interviewing (progress solid) →
 *   Offered (positive outline) → Hired (positive solid) →
 *   Rejected/Withdrawn (muted terminal).
 */
export const APPLICATION_STATUS_TONES: Record<ApplicationStatus, StatusTone> = {
  submitted: "attention",
  reviewed: "progress",
  shortlisted: "positive",
  interviewing: "progressSolid",
  offered: "positiveOutline",
  hired: "positiveSolid",
  rejected: "muted",
  withdrawn: "muted",
};

/* ── Domain: interview scheduling ─────────────────────────────────────── */
export const INTERVIEW_STATUS_TONES: Record<string, StatusTone> = {
  proposed: "progress",
  pending: "progress",
  awaiting_reply: "progress",
  confirmed: "positive",
  accepted: "positive",
  scheduled: "positive",
  completed: "muted",
  declined: "muted",
  cancelled: "muted",
  no_show: "attention",
};

/* ── Domain: credentials & verification ─────────────────────────────────
 * A credential's NAME chip has ONE base style everywhere — neutral.
 * Verification level is an affix chip/icon, never a recolor of the name.
 */
export const CREDENTIAL_CHIP_CLASS = `${STATUS_CHIP_BASE} ${STATUS_TONE_CLASSES.neutral}`;

export const VERIFICATION_LEVEL_META: Record<
  number,
  { label: string; tone: StatusTone }
> = {
  2: { label: "SKILLED-verified", tone: "positive" },
  1: { label: "Institution-verified", tone: "positive" },
  0: { label: "Self-reported", tone: "neutral" },
};

/* ── Domain: sync / import health ───────────────────────────────────────
 * ok/healthy → positive · running/pending → progress · stale → attention ·
 * failed/error → danger · disabled/paused/draft → muted.
 */
export const HEALTH_TONES: Record<string, StatusTone> = {
  ok: "positive",
  healthy: "positive",
  success: "positive",
  approved: "positive",
  published: "positive",
  live: "positive",
  running: "progress",
  pending: "progress",
  syncing: "progress",
  processing: "progress",
  in_review: "progress",
  stale: "attention",
  needs_review: "attention",
  rejected: "attention",
  failed: "danger",
  error: "danger",
  disabled: "muted",
  paused: "muted",
  draft: "muted",
  archived: "muted",
  expired: "muted",
};
