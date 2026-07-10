"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";
import { MonoLabel, Field } from "@/components/ui";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [resendState, setResendState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const router = useRouter();

  async function handleResend() {
    if (!email || resendState === "sending") return;
    setResendState("sending");
    const supabase = createClient();
    const { error: resendErr } = await supabase.auth.resend({
      type: "signup",
      email,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });
    if (resendErr) setResendState("error");
    else setResendState("sent");
  }

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

      await supabase.auth.refreshSession();

      router.push("/applicant");
      router.refresh();
      return;
    }

    setDone(true);
    setLoading(false);
  }

  if (done) {
    return (
      <div className="text-center">
        <MonoLabel className="mb-4 block">Almost there</MonoLabel>
        <h2 className="font-display text-card text-cohere-ink">Check your email</h2>
        <p className="mt-3 text-body text-slate">
          We sent a confirmation link to{" "}
          <strong className="text-ink">{email}</strong>. Click it to finish creating
          your account. The link expires in 24 hours.
        </p>
        <p className="mt-3 text-caption text-slate">
          Don&apos;t see it? Check your spam folder, or resend below.
        </p>

        <div className="mt-6 flex flex-col items-center gap-3">
          <button
            type="button"
            onClick={handleResend}
            disabled={resendState === "sending" || resendState === "sent"}
            className="btn-secondary inline-flex disabled:opacity-60"
          >
            {resendState === "sending"
              ? "Sending…"
              : resendState === "sent"
                ? "Resent — check your inbox"
                : "Resend confirmation email"}
          </button>
          {resendState === "error" && (
            <p className="text-caption text-error-red">Couldn&apos;t resend right now. Try again in a moment.</p>
          )}
          <Link
            href="/login"
            className="text-caption text-cohere-blue underline underline-offset-4 hover:text-cohere-ink"
          >
            Already verified? Sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div>
      <MonoLabel className="mb-4 block">Get started</MonoLabel>
      <h1 className="font-display text-card text-cohere-ink">Create account</h1>
      <p className="mt-2 text-body text-slate">
        Applicants only — employers are added by invitation.
      </p>

      <form onSubmit={handleSignup} className="mt-8 space-y-5">
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

        <Field label="Password" hint="Minimum 8 characters.">
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

        <Field label="Confirm password">
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
          {loading ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-8 text-caption text-slate">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-cohere-blue underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </div>
  );
}
