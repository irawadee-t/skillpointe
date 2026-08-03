import type { Transition } from "motion/react";

/** Cohere easing — carved, decisive settle. */
export const easeCohere: Transition["ease"] = [0.16, 1, 0.3, 1];

/**
 * RISE_IN — subtle entrance for newly appended thread content: 200ms
 * ease-out, 8px rise (the `fade-up` keyframe in tailwind.config.ts). The
 * global prefers-reduced-motion rule in globals.css collapses it to an
 * instant appearance, so it is motion-safe by construction.
 *
 * Apply it ONLY to content that is genuinely new (a message that just
 * arrived, a row that just appeared) — never to content re-rendered by a
 * poll cycle. Callers keep key stability and track "seen" ids so existing
 * messages never re-animate.
 */
export const RISE_IN = "animate-[fade-up_200ms_cubic-bezier(0.16,1,0.3,1)_both]";

/** Quicker variant for micro-elements (badges, pills): 150ms fade. */
export const FADE_IN_FAST = "animate-[fade-in_150ms_ease_both]";
