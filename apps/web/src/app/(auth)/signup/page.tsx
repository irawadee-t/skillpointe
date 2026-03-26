"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const router = useRouter();

  async function handleSignup(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setLoading(true);

    const supabase = createClient();
    const { data, error: authError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    });

    if (authError) {
      setError(authError.message);
      setLoading(false);
      return;
    }

    // If email confirmations are disabled (local dev default), user has a session.
    // Call the API to finalize profile creation and embed role in JWT.
    if (data.session) {
      const accessToken = data.session.access_token;

      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/auth/complete-signup`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
        }
      );

      if (!resp.ok) {
        setError("Signup succeeded but profile setup failed. Please contact support.");
        setLoading(false);
        return;
      }

      // Refresh session so JWT picks up the new app_metadata.role
      await supabase.auth.refreshSession();

      router.push("/applicant");
      router.refresh();
      return;
    }

    // Email confirmations enabled — show "check your email" message
    setDone(true);
    setLoading(false);
  }

  if (done) {
    return (
      <div className="flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm bg-zinc-900 border border-zinc-800 rounded-2xl p-8 text-center">
          <h2 className="text-xl font-semibold mb-3 text-white">Check your email</h2>
          <p className="text-zinc-400 text-sm">
            We sent a confirmation link to <strong className="text-white">{email}</strong>. Click the
            link to finish creating your account.
          </p>
          <Link href="/login" className="mt-6 inline-block text-cyan-400 hover:text-cyan-300 underline text-sm">
            Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm bg-zinc-900 border border-zinc-800 rounded-2xl p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-white mb-1">Create account</h1>
        <p className="text-sm text-zinc-400 mb-6">
          Applicants only — employers are added by invitation.
        </p>

        <form onSubmit={handleSignup} className="space-y-4">
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

          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-zinc-500 mb-1">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
              className="w-full border border-zinc-700 rounded-lg px-3 py-2.5 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
            />
            <p className="text-xs text-zinc-500 mt-1">Minimum 8 characters.</p>
          </div>

          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-zinc-500 mb-1">
              Confirm password
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full border border-zinc-700 rounded-lg px-3 py-2.5 text-sm bg-zinc-900 text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500"
            />
          </div>

          {error && (
            <p className="text-sm text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded p-3">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-cyan-500 text-black py-2.5 rounded-full text-sm font-medium hover:bg-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-sm text-zinc-400">
          Already have an account?{" "}
          <Link href="/login" className="text-cyan-400 hover:text-cyan-300 underline font-medium">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
