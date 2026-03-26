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

    // Redirect to role dashboard
    const role = data.user?.app_metadata?.role as string | undefined;
    router.push(role ? (ROLE_HOME[role] ?? "/login") : "/login");
    router.refresh();
  }

  return (
    <div className="flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm bg-zinc-900 border border-zinc-800 rounded-2xl p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-white mb-1">Set new password</h1>
        <p className="text-sm text-zinc-400 mb-6">
          Choose a new password for your account.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-zinc-500 mb-1">
              New password
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
          </div>

          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-zinc-500 mb-1">
              Confirm new password
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
            className="w-full bg-cyan-500 text-black py-2.5 rounded-full text-sm font-medium hover:bg-cyan-400 disabled:opacity-50 transition-colors"
          >
            {loading ? "Updating…" : "Update password"}
          </button>
        </form>
      </div>
    </div>
  );
}
