"use client";

import { useCallback, useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";

/**
 * Dialog — the ONE accessible modal primitive for the product.
 *
 * Semantics: role="dialog", aria-modal, labelled by its title. Escape closes,
 * focus moves in on open and is restored on close, Tab is trapped, backdrop
 * click closes. Surface follows the contract: white sheet, hairline border,
 * `shadow-float` (the single elevation token), 14px radius, flat otherwise.
 *
 * `ConfirmDialog` layers the standard confirm pattern on top (consequence
 * copy + cancel/commit buttons) — used by matching activation and dashboard
 * recompute so destructive-ish actions share one behavior.
 */
export function Dialog({
  open, onClose, title, children, labelledBy, wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  labelledBy?: string;
  wide?: boolean;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  const focusables = useCallback((): HTMLElement[] => {
    const root = panelRef.current;
    if (!root) return [];
    return Array.from(
      root.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((el) => el.offsetParent !== null);
  }, []);

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = (document.activeElement as HTMLElement) ?? null;
    const t = setTimeout(() => {
      const els = focusables();
      (els[0] ?? panelRef.current)?.focus();
    }, 10);

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const els = focusables();
      if (els.length === 0) { e.preventDefault(); return; }
      const first = els[0];
      const last = els[els.length - 1];
      const active = document.activeElement as HTMLElement | null;
      const inside = active ? panelRef.current?.contains(active) : false;
      if (e.shiftKey) {
        if (!inside || active === first) { e.preventDefault(); last.focus(); }
      } else if (!inside || active === last) {
        e.preventDefault(); first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      document.removeEventListener("keydown", onKey);
      previouslyFocused.current?.focus?.();
    };
  }, [open, onClose, focusables]);

  if (!open) return null;

  const titleId = labelledBy ?? "dialog-title";
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-ink/30 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`relative w-full ${wide ? "max-w-2xl" : "max-w-md"} rounded-[14px] border border-hairline bg-white shadow-float focus:outline-none`}
      >
        <div className="border-b border-hairline px-5 py-3.5">
          <h2 id={titleId} className="text-[1.0625rem] font-medium text-cohere-ink">{title}</h2>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open, onClose, onConfirm, title, body, confirmLabel = "Confirm",
  cancelLabel = "Cancel", busy = false, danger = false, disabled = false,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  body: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <Dialog open={open} onClose={busy ? () => {} : onClose} title={title}>
      <div className="space-y-4">
        <div className="text-body text-slate">{body}</div>
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            disabled={busy}
            className="rounded-full border border-hairline bg-white px-4 py-1.5 text-body text-cohere-ink transition-colors hover:bg-stone disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            disabled={busy || disabled}
            className={`inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-body font-medium text-white transition-colors disabled:opacity-50 ${
              danger ? "bg-studio-maroon hover:bg-[#8a1e2f]" : "bg-ink hover:bg-black"
            }`}
          >
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </Dialog>
  );
}
