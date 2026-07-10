"use client";

import { AlertCircle, RotateCw, Copy } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Consistent inline error UI with retry + optional debug-copy.
 *
 * Never leaves the user staring at a dead "Could not reach the API" message.
 * The retry button gives them agency; the copy-error button gives support a
 * reproduction string to work with.
 */
export function ErrorState({
  title = "Something went wrong",
  message,
  detail,
  onRetry,
  className,
}: {
  title?: string;
  message?: string;
  /** Full error detail (stack, request ID, etc). Never shown by default; revealed via "Copy error details". */
  detail?: string;
  onRetry?: () => void | Promise<unknown>;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const doCopy = async () => {
    const payload = `${title}\n${message ?? ""}\n${detail ?? ""}`.trim();
    try {
      await navigator.clipboard.writeText(payload);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* ignore */ }
  };

  const doRetry = async () => {
    if (!onRetry) return;
    setRetrying(true);
    try { await onRetry(); } finally { setRetrying(false); }
  };

  return (
    <div className={cn("rounded-lg border border-studio-maroon/30 bg-studio-maroon/5 p-4 text-[13px]", className)}>
      <div className="flex items-start gap-2 text-cohere-ink">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-studio-maroon" strokeWidth={2} />
        <div className="min-w-0 flex-1">
          <p className="font-medium">{title}</p>
          {message && <p className="mt-0.5 text-slate">{message}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            {onRetry && (
              <button
                type="button"
                onClick={doRetry}
                disabled={retrying}
                className="btn-primary-sm inline-flex items-center gap-1"
              >
                <RotateCw className={cn("h-3 w-3", retrying && "animate-spin")} />
                {retrying ? "Retrying…" : "Retry"}
              </button>
            )}
            {detail && (
              <button
                type="button"
                onClick={doCopy}
                className="inline-flex items-center gap-1 text-[12px] text-slate underline decoration-hairline underline-offset-2 hover:text-cohere-ink"
              >
                <Copy className="h-3 w-3" />
                {copied ? "Copied" : "Copy error details"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
