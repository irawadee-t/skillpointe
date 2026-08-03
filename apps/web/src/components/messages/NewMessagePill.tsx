"use client";

/**
 * Quiet "↓ New message" affordance for thread surfaces. Shown (via
 * useStickToBottom's `hasUnseen`) when content arrives while the reader has
 * scrolled up — the view is never yanked; this is the invitation back down.
 *
 * Render inside a `relative` wrapper that overlays the scroll container:
 *
 *   <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
 *     <NewMessagePill onClick={() => scrollToBottom({ smooth: true })} />
 *   </div>
 */
import { ArrowDown } from "lucide-react";

import { RISE_IN } from "@/lib/motion";

export function NewMessagePill({
  onClick,
  label = "New message",
}: {
  onClick: () => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`pointer-events-auto inline-flex items-center gap-1.5 rounded-full bg-ink px-3 py-1.5 text-micro font-medium text-white shadow-float transition-opacity hover:opacity-90 ${RISE_IN}`}
    >
      <ArrowDown className="h-3 w-3" aria-hidden />
      {label}
    </button>
  );
}
