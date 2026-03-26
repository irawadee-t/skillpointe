"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { createClient } from "@/lib/supabase/client";

const ROLE_HOME: Record<string, string> = {
  applicant: "/applicant",
  employer: "/employer",
  admin: "/admin",
};

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const router = useRouter();
  const searchParams = useSearchParams();

  const nextPath = searchParams.get("next");

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const supabase = createClient();
    const { data, error: authError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (authError) {
      setError(authError.message);
      setLoading(false);
      return;
    }

    let role = data.user?.app_metadata?.role as string | undefined;

    // If no role is set, the user signed up but complete-signup never ran
    // (e.g. API was down during signup). Finalize their profile now.
    if (!role && data.session) {
      try {
        const resp = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/auth/complete-signup`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${data.session.access_token}` },
          }
        );
        if (resp.ok) {
          await supabase.auth.refreshSession();
          role = "applicant";
        }
      } catch {
        // Non-fatal — will redirect to "/" and they can try again
      }
    }

    const destination = nextPath ?? (role ? ROLE_HOME[role] : null) ?? "/";
    router.push(destination);
    router.refresh();
  }

  return (
    <div className="flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm bg-zinc-900 border border-zinc-800 rounded-2xl p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-white mb-1">Sign in</h1>
        <p className="text-sm text-zinc-400 mb-6">SkillPointe Match</p>

        {searchParams.get("error") === "auth_callback_failed" && (
          <p className="mb-4 text-sm text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded p-3">
            Authentication failed. Please try again.
          </p>
        )}

        <form onSubmit={handleLogin} className="space-y-4">
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
              autoComplete="current-password"
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
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-6 text-sm space-y-2 text-zinc-400">
          <p>
            New applicant?{" "}
            <Link href="/signup" className="text-cyan-400 hover:text-cyan-300 underline font-medium">
              Create account
            </Link>
          </p>
          <p>
            <Link href="/forgot-password" className="text-zinc-500 hover:text-zinc-300 underline">
              Forgot password?
            </Link>
          </p>
        </div>

        <p className="mt-6 text-xs text-zinc-500">
          Employers and admins are added by invitation only. Contact SkillPointe
          if you need access.
        </p>
      </div>
    </div>
  );
}
