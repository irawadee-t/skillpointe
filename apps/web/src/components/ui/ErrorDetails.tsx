"use client";

/**
 * Quiet disclosure for API error metadata.
 *
 * Surfaces that show a human error sentence can drop this underneath to let
 * users (or support) grab the request id without ever rendering raw JSON.
 * Renders nothing when there's no useful metadata.
 */
import { ApiError } from "@/lib/api/client";

export function ErrorDetails({ error, className = "" }: { error: unknown; className?: string }) {
  if (!(error instanceof ApiError)) return null;
  if (!error.requestId && !error.status) return null;
  return (
    <details className={`mt-1.5 ${className}`}>
      <summary className="cursor-pointer select-none text-micro text-slate-muted hover:text-slate">
        Error details
      </summary>
      <p className="mt-1 text-micro text-slate-muted">
        {error.requestId ? (
          <>
            Reference id <code className="tabular-nums">{error.requestId}</code>
            {" · "}
          </>
        ) : null}
        HTTP {error.status}
        {". Share this with support if the problem continues."}
      </p>
    </details>
  );
}
