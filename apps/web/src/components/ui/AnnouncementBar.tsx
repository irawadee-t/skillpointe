"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

/** Full-width black announcement strip above the nav. */
export function AnnouncementBar({
  children,
}: {
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  const prefersReducedMotion = useReducedMotion();
  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          role="region"
          aria-label="Announcement"
          initial={prefersReducedMotion ? false : { height: 0, opacity: 0 }}
          animate={prefersReducedMotion ? { height: 36, opacity: 1 } : { height: 36, opacity: 1 }}
          exit={prefersReducedMotion ? { opacity: 0 } : { height: 0, opacity: 0 }}
          transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          className="overflow-hidden bg-cohere-black text-white"
        >
          <div className="container-cohere flex h-9 items-center justify-center">
            <p className="text-caption text-white/90">{children}</p>
            <button
              onClick={() => setOpen(false)}
              aria-label="Dismiss announcement"
              className="absolute right-5 text-white/60 transition-colors hover:text-white focus-visible:outline-2 focus-visible:outline-white focus-visible:outline-offset-2 focus-visible:rounded-sm sm:right-8 lg:right-12"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
