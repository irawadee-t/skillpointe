"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Check } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { MonoLabel, Field } from "@/components/ui";
import { PasswordInput } from "@/components/ui/PasswordInput";

const MIN_PASSWORD_LENGTH = 8;

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  // Field-level validation errors (Stripe-style inline validation): the
  // message renders at the field, not below the form. The bottom box is
  // reserved for server/network errors only.
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [resendState, setResendState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  const router = useRouter();

  const passwordLongEnough = password.length >= MIN_PASSWORD_LENGTH;

  function validatePasswordOnBlur() {
    if (password && !passwordLongEnough) {
      setPasswordError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
    }
  }

  function validateConfirmOnBlur() {
    if (confirmPassword && confirmPassword !== password) {
      setConfirmError("Passwords don't match.");
    }
  }

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

    // Final check before submit — errors land on the fields themselves.
    let firstInvalid: string | null = null;
    if (!passwordLongEnough) {
      setPasswordError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      firstInvalid = firstInvalid ?? "password";
    }
    if (password !== confirmPassword) {
      setConfirmError("Passwords don't match.");
      firstInvalid = firstInvalid ?? "confirm-password";
    }
    if (firstInvalid) {
      (document.getElementById(`signup-${firstInvalid}`) as HTMLInputElement | null)?.focus();
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

      try {
        const resp = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/auth/complete-signup`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${accessToken}` },
          }
        );

        if (!resp.ok) {
          setError("Signup succeeded but profile setup failed. Please contact support.");
          return;
        }

        await supabase.auth.refreshSession();

        // Brand-new accounts go straight into the setup wizard — the profile is
        // empty, so the dashboard would just be a wall of "Not set" cards.
        router.push("/applicant/setup");
        router.refresh();
      } catch {
        setError("Couldn't reach the server to finish setting up your account. Check your connection and try again.");
      } finally {
        setLoading(false);
      }
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
                ? "Resent. Check your inbox"
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
        Applicants only. Employers are added by invitation.
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

        <Field label="Password" error={passwordError}>
          <PasswordInput
            id="signup-password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              // Live validation: clear the error the moment it's satisfied.
              if (e.target.value.length >= MIN_PASSWORD_LENGTH) setPasswordError(null);
              if (confirmError && confirmPassword === e.target.value) setConfirmError(null);
            }}
            onBlur={validatePasswordOnBlur}
            aria-invalid={!!passwordError}
            aria-describedby="signup-password-rule"
            required
            autoComplete="new-password"
          />
          {/* Live requirement hint — flips to a check the moment it's met. */}
          <p
            id="signup-password-rule"
            aria-live="polite"
            className={`mt-1.5 flex items-center gap-1.5 text-micro transition-colors ${
              passwordLongEnough ? "text-cohere-green" : "text-slate-muted"
            }`}
          >
            {passwordLongEnough ? (
              <Check className="h-3 w-3" aria-hidden />
            ) : (
              <span aria-hidden className="inline-block h-1 w-1 rounded-full bg-current" />
            )}
            {MIN_PASSWORD_LENGTH}+ characters
          </p>
        </Field>

        <Field label="Confirm password" error={confirmError}>
          <PasswordInput
            id="signup-confirm-password"
            value={confirmPassword}
            onChange={(e) => {
              setConfirmPassword(e.target.value);
              // Clear the mismatch error as soon as the fields agree.
              if (e.target.value === password) setConfirmError(null);
            }}
            onBlur={validateConfirmOnBlur}
            aria-invalid={!!confirmError}
            required
            autoComplete="new-password"
          />
        </Field>

        {error && (
          <p className="rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
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
