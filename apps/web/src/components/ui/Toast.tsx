"use client";

import {
  createContext, useCallback, useContext, useEffect, useRef, useState,
} from "react";
import { CheckCircle2, AlertTriangle, Info, X, Undo2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Toast provider — mounted once in the dashboard layout.
 *
 * Usage:
 *   const toast = useToast();
 *   toast.success("Application sent");
 *   toast.undo("Marked not interested", async () => { await unmark(); });
 *   toast.error("Something went wrong");
 *   toast.info("Interview scheduled for Friday 2 PM");
 *
 * Design: floating pill bottom-right on desktop, bottom-full on mobile. Same
 * chip vocabulary as the rest of the site (rounded, hairline border, wash
 * tones by intent). Auto-dismiss after 3s (or 8s for undo).
 */

type Intent = "success" | "error" | "info" | "undo";

interface ToastItem {
  id: string;
  intent: Intent;
  message: string;
  undo?: () => void | Promise<void>;
  duration: number;
}

interface ToastAPI {
  success: (msg: string, opts?: { duration?: number }) => void;
  error:   (msg: string, opts?: { duration?: number }) => void;
  info:    (msg: string, opts?: { duration?: number }) => void;
  undo:    (msg: string, onUndo: () => void | Promise<void>, opts?: { duration?: number }) => void;
  dismiss: (id: string) => void;
}

const Ctx = createContext<ToastAPI | null>(null);

export function useToast(): ToastAPI {
  const v = useContext(Ctx);
  if (!v) throw new Error("useToast must be used inside <ToastProvider>");
  return v;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
    const t = timersRef.current.get(id);
    if (t) { clearTimeout(t); timersRef.current.delete(id); }
  }, []);

  const push = useCallback((item: Omit<ToastItem, "id">) => {
    const id = Math.random().toString(36).slice(2, 10);
    setItems((prev) => [...prev.slice(-4), { ...item, id }]);
    const timer = setTimeout(() => dismiss(id), item.duration);
    timersRef.current.set(id, timer);
    return id;
  }, [dismiss]);

  const api: ToastAPI = {
    success: (message, opts) => { push({ intent: "success", message, duration: opts?.duration ?? 3000 }); },
    error:   (message, opts) => { push({ intent: "error",   message, duration: opts?.duration ?? 5000 }); },
    info:    (message, opts) => { push({ intent: "info",    message, duration: opts?.duration ?? 4000 }); },
    undo:    (message, onUndo, opts) => {
      push({ intent: "undo", message, undo: onUndo, duration: opts?.duration ?? 8000 });
    },
    dismiss,
  };

  useEffect(() => () => {
    for (const t of timersRef.current.values()) clearTimeout(t);
    timersRef.current.clear();
  }, []);

  return (
    <Ctx.Provider value={api}>
      {children}
      <ToastViewport items={items} onDismiss={dismiss} />
    </Ctx.Provider>
  );
}

const INTENT_STYLE: Record<Intent, { Icon: typeof CheckCircle2; wash: string; iconClass: string }> = {
  success: { Icon: CheckCircle2,  wash: "border-cohere-green/30  bg-wash-green",             iconClass: "text-cohere-green" },
  error:   { Icon: AlertTriangle, wash: "border-studio-maroon/30  bg-studio-maroon/[0.08]",    iconClass: "text-studio-maroon" },
  info:    { Icon: Info,          wash: "border-cohere-blue/30   bg-wash-blue",              iconClass: "text-cohere-blue"  },
  undo:    { Icon: Undo2,         wash: "border-hairline         bg-white",                  iconClass: "text-slate"        },
};

function ToastViewport({ items, onDismiss }: { items: ToastItem[]; onDismiss: (id: string) => void }) {
  return (
    <div
      aria-live="polite" aria-atomic="true"
      className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4 sm:bottom-6 sm:right-6 sm:left-auto sm:items-end"
    >
      {items.map((t) => (
        <ToastCard key={t.id} item={t} onDismiss={() => onDismiss(t.id)} />
      ))}
    </div>
  );
}

function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  const [busy, setBusy] = useState(false);
  const { Icon, wash, iconClass } = INTENT_STYLE[item.intent];

  async function handleUndo() {
    if (!item.undo || busy) return;
    setBusy(true);
    try { await item.undo(); } finally { onDismiss(); }
  }

  return (
    <div
      role={item.intent === "error" ? "alert" : "status"}
      className={cn(
        "pointer-events-auto flex w-full max-w-sm items-start gap-2.5 rounded-xl border px-4 py-3 shadow-[0_18px_44px_-14px_rgba(12,10,9,0.20)]",
        "animate-[toastIn_180ms_ease-out]",
        wash,
      )}
    >
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", iconClass)} strokeWidth={2} />
      <p className="flex-1 text-body text-cohere-ink">{item.message}</p>
      {item.undo && (
        <button
          onClick={handleUndo}
          disabled={busy}
          className="ml-2 shrink-0 rounded-full border border-cohere-ink px-2.5 py-0.5 text-micro font-medium text-cohere-ink transition-colors hover:bg-studio-dark-cork hover:text-canvas disabled:opacity-40"
        >
          Undo
        </button>
      )}
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        className="ml-1 shrink-0 rounded p-0.5 text-slate-muted transition-colors hover:text-cohere-ink"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
