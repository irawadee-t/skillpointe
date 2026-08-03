"use client";

import Link from "next/link";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";
import { MonoLabel, Field } from "@/components/ui";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const supabase = createClient();
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/callback?type=recovery`,
    });

    setLoading(false);

    if (resetError) {
      setError(resetError.message);
      return;
    }

    setSent(true);
  }

  if (sent) {
    return (
      <div className="text-center">
        <MonoLabel className="mb-4 block">Reset requested</MonoLabel>
        <h2 className="font-display text-card text-cohere-ink">Check your email</h2>
        <p className="mt-3 text-body text-slate">
          If <strong className="text-ink">{email}</strong> has an account, a password
          reset link is on its way.
        </p>
        <Link href="/login" className="btn-secondary mt-8 inline-flex">
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <div>
      <MonoLabel className="mb-4 block">Account recovery</MonoLabel>
      <h1 className="font-display text-card text-cohere-ink">Reset password</h1>
      <p className="mt-2 text-body text-slate">
        Enter your email and we&apos;ll send a reset link.
      </p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-5">
        <Field label="Email">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            className="input-cohere"
          />
        </Field>

        {error && (
          <p className="rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
            {error}
          </p>
        )}

        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? "Sending…" : "Send reset link"}
        </button>
      </form>

      <p className="mt-8 text-caption text-slate">
        <Link href="/login" className="text-slate-muted underline underline-offset-4 hover:text-ink">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
