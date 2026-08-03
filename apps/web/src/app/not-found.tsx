import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-canvas px-6 text-center">
      <p className="text-micro font-medium uppercase tracking-[0.16em] text-studio-maroon">
        404 · Page not found
      </p>
      <h1 className="mt-5 font-display text-heading text-cohere-ink">
        We couldn&rsquo;t find that page.
      </h1>
      <p className="mt-4 max-w-md text-body text-slate">
        The link may be broken, or the page may have moved. Let&rsquo;s get you back
        to something useful.
      </p>
      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <Link href="/" className="btn-primary">
          Back to home
        </Link>
        <Link href="/login" className="btn-secondary">
          Sign in
        </Link>
      </div>
    </main>
  );
}
