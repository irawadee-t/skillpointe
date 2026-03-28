"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

const ROLE_HOME: Record<string, string> = {
  applicant: "/applicant",
  employer: "/employer",
  admin: "/admin",
};

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
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

    const { data, error: updateError } = await supabase.auth.updateUser({
      password,
    });

    setLoading(false);

    if (updateError) {
      setError(updateError.message);
      return;
    }

    const role = data.user?.app_metadata?.role as string | undefined;
    router.push(role ? (ROLE_HOME[role] ?? "/login") : "/login");
    router.refresh();
  }

  return (
    <div className="flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm bg-white border border-zinc-200 rounded-2xl p-8 shadow-sm">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 mb-1">Set new password</h1>
        <p className="text-sm text-zinc-500 mb-6">
          Choose a new password for your account.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-zinc-400 mb-1">
              New password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
              className="w-full border border-zinc-200 rounded-lg px-3 py-2.5 text-sm bg-white text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-spf-navy/20 focus:border-spf-navy"
            />
          </div>

          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-zinc-400 mb-1">
              Confirm new password
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full border border-zinc-200 rounded-lg px-3 py-2.5 text-sm bg-white text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-spf-navy/20 focus:border-spf-navy"
            />
          </div>

          {error && (
            <p className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded p-3">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-zinc-900 text-white py-2.5 rounded-full text-sm font-medium hover:bg-zinc-700 disabled:opacity-50 transition-colors"
          >
            {loading ? "Updating…" : "Update password"}
          </button>
        </form>
      </div>
    </div>
  );
}
