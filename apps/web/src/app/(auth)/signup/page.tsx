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
        <div className="w-full max-w-sm bg-white border border-neutral-200 rounded-2xl p-8 text-center">
          <h2 className="text-xl font-semibold mb-3 text-neutral-900">Check your email</h2>
          <p className="text-neutral-500 text-sm">
            We sent a confirmation link to <strong>{email}</strong>. Click the
            link to finish creating your account.
          </p>
          <Link href="/login" className="mt-6 inline-block text-neutral-500 hover:text-neutral-900 underline text-sm">
            Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm bg-white border border-neutral-200 rounded-2xl p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900 mb-1">Create account</h1>
        <p className="text-sm text-neutral-400 mb-6">
          Applicants only — employers are added by invitation.
        </p>

        <form onSubmit={handleSignup} className="space-y-4">
          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500 mb-1">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="w-full border border-neutral-200 rounded-lg px-3 py-2.5 text-sm bg-white text-neutral-900 focus:outline-none focus:ring-1 focus:ring-neutral-400"
            />
          </div>

          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500 mb-1">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
              className="w-full border border-neutral-200 rounded-lg px-3 py-2.5 text-sm bg-white text-neutral-900 focus:outline-none focus:ring-1 focus:ring-neutral-400"
            />
            <p className="text-xs text-neutral-400 mt-1">Minimum 8 characters.</p>
          </div>

          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500 mb-1">
              Confirm password
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full border border-neutral-200 rounded-lg px-3 py-2.5 text-sm bg-white text-neutral-900 focus:outline-none focus:ring-1 focus:ring-neutral-400"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded p-3">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-neutral-900 text-white py-2.5 rounded-full text-sm font-medium hover:bg-neutral-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-sm text-neutral-600">
          Already have an account?{" "}
          <Link href="/login" className="text-neutral-500 hover:text-neutral-900 underline font-medium">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
