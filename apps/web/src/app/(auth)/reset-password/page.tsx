"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";
import { MonoLabel, Field } from "@/components/ui";

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

    const { data, error: updateError } = await supabase.auth.updateUser({ password });

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
    <div>
      <MonoLabel className="mb-4 block">New credentials</MonoLabel>
      <h1 className="font-display text-card text-cohere-ink">Set new password</h1>
      <p className="mt-2 text-body text-slate">Choose a new password for your account.</p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-5">
        <Field label="New password" hint="Minimum 8 characters.">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            className="input-cohere"
          />
        </Field>

        <Field label="Confirm new password">
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            autoComplete="new-password"
            className="input-cohere"
          />
        </Field>

        {error && (
          <p className="rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-error-red">
            {error}
          </p>
        )}

        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? "Updating…" : "Update password"}
        </button>
      </form>
    </div>
  );
}
