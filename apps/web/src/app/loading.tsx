export default function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas">
      <div className="flex flex-col items-center gap-4" role="status" aria-live="polite">
        <span
          className="h-8 w-8 animate-spin rounded-full border-2 border-hairline border-t-studio-maroon motion-reduce:animate-none"
          aria-hidden
        />
        <span className="text-micro uppercase tracking-[0.14em] text-slate-muted">
          Loading…
        </span>
      </div>
    </div>
  );
}
