"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface to the console (and Sentry, once wired) so failures aren't silent.
    console.error(error);
  }, [error]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-canvas px-6 text-center">
      <p className="text-micro font-medium uppercase tracking-[0.16em] text-error-red">
        Something went wrong
      </p>
      <h1 className="mt-5 font-display text-heading text-cohere-ink">
        This page failed to load.
      </h1>
      <p className="mt-4 max-w-md text-body text-slate">
        Something on our end failed to load. Try again, and if it
        keeps happening, let us know.
      </p>
      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <button onClick={() => reset()} className="btn-primary">
          Try again
        </button>
        {/* A hard navigation (window.location) is intentional here: from an
            error boundary we want to fully reset any broken client state rather
            than client-side navigate back into it. */}
        <button
          onClick={() => {
            window.location.href = "/";
          }}
          className="btn-secondary"
        >
          Back to home
        </button>
      </div>
      {error.digest && (
        <p className="mt-6 text-micro text-slate-muted">Reference: {error.digest}</p>
      )}
    </main>
  );
}
