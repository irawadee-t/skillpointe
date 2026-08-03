"use client";

import { MotionConfig } from "motion/react";

/**
 * App-wide Motion config: when the OS asks for reduced motion, Motion drops
 * transform/layout animation but keeps opacity — gentler, not zero. The CSS
 * reduced-motion block in globals.css cannot reach Motion's JS-driven inline
 * styles; this provider is what honors the preference for every `motion.*`
 * component in the tree.
 */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
