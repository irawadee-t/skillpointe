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
      <div className="w-full max-w-md bg-white rounded-xl shadow p-8">
        <h1 className="text-2xl font-bold text-spf-navy mb-1">Sign in</h1>
        <p className="text-sm text-gray-500 mb-6">SkillPointe Match</p>

        {searchParams.get("error") === "auth_callback_failed" && (
          <p className="mb-4 text-sm text-red-600 bg-red-50 rounded p-3">
            Authentication failed. Please try again.
          </p>
        )}

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-spf-navy/40"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-spf-navy/40"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded p-3">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-spf-navy text-white py-2 rounded-md text-sm font-medium hover:bg-spf-navy-light disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-6 text-sm space-y-2 text-gray-600">
          <p>
            New applicant?{" "}
            <Link href="/signup" className="text-spf-orange hover:underline font-medium">
              Create account
            </Link>
          </p>
          <p>
            <Link href="/forgot-password" className="text-spf-navy hover:underline">
              Forgot password?
            </Link>
          </p>
        </div>

        <p className="mt-6 text-xs text-gray-400">
          Employers and admins are added by invitation only. Contact SkillPointe
          if you need access.
        </p>
      </div>
    </div>
  );
}
