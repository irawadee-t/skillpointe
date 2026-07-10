"use client";

/**
 * Small client-side error card shown when the applicant dashboard fails to
 * reach the API. Provides a retry that re-runs the server fetch via
 * router.refresh() so we don't lose scroll/state on the way back.
 */
import { useRouter } from "next/navigation";
import { useState } from "react";
import { RefreshCw, Loader2 } from "lucide-react";

export function ApiUnreachable() {
  const router = useRouter();
  const [retrying, setRetrying] = useState(false);

  function handleRetry() {
    setRetrying(true);
    router.refresh();
    // Give the refresh a moment; if we're still mounted (e.g. still failing)
    // release the button so the user can try again.
    setTimeout(() => setRetrying(false), 1500);
  }

  return (
    <main className="py-8">
      <div className="page-shell">
        <div className="bg-studio-maroon/10 border border-studio-maroon-soft rounded-md p-5 text-body text-error-red flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <strong>Could not reach the API.</strong>{" "}
            <span className="text-cohere-ink/80">
              The backend may be starting up — try again in a moment.
            </span>
          </div>
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="btn-secondary inline-flex items-center gap-1.5 self-start sm:self-auto disabled:opacity-60"
          >
            {retrying ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            {retrying ? "Retrying…" : "Try again"}
          </button>
        </div>
      </div>
    </main>
  );
}
