"use client";

import Link from "next/link";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

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
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(
      email,
      {
        redirectTo: `${window.location.origin}/auth/callback?type=recovery`,
      }
    );

    setLoading(false);

    if (resetError) {
      setError(resetError.message);
      return;
    }

    setSent(true);
  }

  if (sent) {
    return (
      <div className="flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm bg-zinc-900 border border-zinc-800 rounded-2xl p-8 text-center">
          <h2 className="text-xl font-semibold mb-3 text-white">Check your email</h2>
          <p className="text-zinc-400 text-sm">
            If <strong className="text-white">{email}</strong> has an account, you will receive a
            password reset link shortly.
          </p>
          <Link
            href="/login"
            className="mt-6 inline-block text-cyan-400 hover:text-cyan-300 underline text-sm"
          >
            Back to login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm bg-zinc-900 border border-zinc-800 rounded-2xl p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-white mb-1">Reset password</h1>
        <p className="text-sm text-zinc-400 mb-6">
          Enter your email and we will send a reset link.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-zinc-500 mb-1">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="w-full border border-zinc-700 rounded-lg px-3 py-2.5 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
            />
          </div>

          {error && (
            <p className="text-sm text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded p-3">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-cyan-500 text-black py-2.5 rounded-full text-sm font-medium hover:bg-cyan-400 disabled:opacity-50 transition-colors"
          >
            {loading ? "Sending…" : "Send reset link"}
          </button>
        </form>

        <p className="mt-6 text-sm text-zinc-400">
          <Link href="/login" className="text-zinc-500 hover:text-zinc-300 underline">
            Back to login
          </Link>
        </p>
      </div>
    </div>
  );
}
