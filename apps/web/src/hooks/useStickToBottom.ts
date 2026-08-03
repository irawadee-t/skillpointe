"use client";

/**
 * useStickToBottom — pinned-to-bottom scroll behavior for chat/thread
 * surfaces. Extracted from the analytics chat's 48px-threshold pattern so
 * every conversational surface (DM threads, planning chat, analytics chat)
 * shares one scroll discipline:
 *
 * - While the reader is at (or within 48px of) the bottom, new content keeps
 *   the view pinned to the bottom.
 * - Once the reader scrolls up, nothing yanks them — instead `hasUnseen`
 *   flips true so the surface can show a quiet "↓ New message" pill.
 * - Sending your own message always scrolls to the bottom, smoothly —
 *   instantly under prefers-reduced-motion.
 */
import { useCallback, useRef, useState } from "react";

const PIN_THRESHOLD_PX = 48;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true
  );
}

export function useStickToBottom<T extends HTMLElement = HTMLDivElement>() {
  const containerRef = useRef<T | null>(null);
  // Whether the reader is currently pinned to the bottom. Starts true — a
  // freshly opened thread reads from its newest message.
  const pinnedRef = useRef(true);
  const [hasUnseen, setHasUnseen] = useState(false);

  /** Attach to the scroll container's onScroll. */
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const pinned =
      el.scrollHeight - el.scrollTop - el.clientHeight < PIN_THRESHOLD_PX;
    pinnedRef.current = pinned;
    if (pinned) setHasUnseen(false);
  }, []);

  /** Scroll to the bottom. Smooth by default; instant under reduced motion. */
  const scrollToBottom = useCallback((opts?: { smooth?: boolean }) => {
    const el = containerRef.current;
    if (!el) return;
    const smooth = (opts?.smooth ?? true) && !prefersReducedMotion();
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    pinnedRef.current = true;
    setHasUnseen(false);
  }, []);

  /**
   * Call after content grows (post-commit, e.g. from an effect watching the
   * message list). `own: true` = the user's own send — always scrolls.
   * Otherwise: scroll only while pinned; when unpinned, raise the pill.
   */
  const onContentAppended = useCallback(
    (opts?: { own?: boolean; smooth?: boolean }) => {
      if (opts?.own || pinnedRef.current) {
        scrollToBottom({ smooth: opts?.smooth });
      } else {
        setHasUnseen(true);
      }
    },
    [scrollToBottom],
  );

  return {
    containerRef,
    handleScroll,
    scrollToBottom,
    onContentAppended,
    hasUnseen,
    pinnedRef,
  };
}
