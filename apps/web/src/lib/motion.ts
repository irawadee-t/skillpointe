import type { Variants, Transition } from "motion/react";

/** Cohere easing — carved, decisive settle. */
export const easeCohere: Transition["ease"] = [0.16, 1, 0.3, 1];

/** Rise-and-fade, the workhorse reveal. */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 20 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: easeCohere },
  },
};

/** Plain fade. */
export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.5, ease: easeCohere } },
};

/** Soft scale-in for cards and media. */
export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.96 },
  show: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.5, ease: easeCohere },
  },
};

/** Parent that staggers its children's reveals. */
export const stagger = (gap = 0.08, delay = 0): Variants => ({
  hidden: {},
  show: {
    transition: { staggerChildren: gap, delayChildren: delay },
  },
});

/** Standard viewport trigger — animate once when ~20% in view. */
export const inView = { once: true, amount: 0.2 } as const;
