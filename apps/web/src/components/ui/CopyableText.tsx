"use client";

import { useState } from "react";
import { Copy, Check } from "lucide-react";

/**
 * Click-to-copy pill for phone/email fields. Shows a small "Copied" state
 * inline for 1.4s, then returns to idle. Falls back gracefully if the
 * Clipboard API is unavailable.
 */
export function CopyableText({ value, className }: { value: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      if (navigator.clipboard) await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* silent */
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      title={copied ? "Copied" : `Copy ${value}`}
      className={`group inline-flex items-center gap-1.5 rounded-md px-1 py-0.5 -mx-1 text-body text-cohere-ink transition-colors hover:bg-stone/60 ${className ?? ""}`}
    >
      <span className="tabular-nums">{value}</span>
      {copied
        ? <Check className="h-3.5 w-3.5 text-cohere-green" strokeWidth={2} />
        : <Copy  className="h-3.5 w-3.5 text-slate-muted opacity-0 transition-opacity group-hover:opacity-100" strokeWidth={1.75} />
      }
    </button>
  );
}
