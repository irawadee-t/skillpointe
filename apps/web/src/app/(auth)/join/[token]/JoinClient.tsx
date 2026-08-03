"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { MonoLabel } from "@/components/ui";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { acceptJoin, acceptJoinSignedIn, type JoinInfo } from "@/lib/api/team";

const MIN_PASSWORD_LENGTH = 8;

/** Honest dead-end for links that can't be used — with the way out. */
function DeadState({ heading, body }: { heading: string; body: string }) {
  return (
    <div>
      <MonoLabel className="mb-4 block">Team invite</MonoLabel>
      <h1 className="font-display text-card text-cohere-ink">{heading}</h1>
      <p className="mt-2 text-body text-slate">{body}</p>
      <p className="mt-8 text-caption text-slate">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-cohere-blue underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </div>
  );
}

export function JoinClient({
  joinToken, info, unknown,
}: {
  joinToken: string;
  info: JoinInfo | null;
  unknown: boolean;
}) {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (unknown || !info) {
    return (
      <DeadState
        heading="This invite link isn't valid"
        body="The link may have been mistyped or replaced by a newer invite. Ask your team to send a fresh one."
      />
    );
  }
  if (info.status === "expired") {
    return (
      <DeadState
        heading="This invite expired"
        body={`Invites are good for 7 days. Ask ${info.inviter_name || "your team"} at ${info.company_name || "the company"} to send a new one.`}
      />
    );
  }
  if (info.status === "revoked") {
    return (
      <DeadState
        heading="This invite was revoked"
        body={`The team at ${info.company_name || "the company"} withdrew this invite. If that's unexpected, check with ${info.inviter_name || "the person who invited you"}.`}
      />
    );
  }
  if (info.status === "used") {
    return (
      <DeadState
        heading="This invite was already used"
        body="An account was already created from this link. Sign in with that account instead."
      />
    );
  }

  const email = info.invited_email ?? "";
  const company = info.company_name ?? "the company";

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < MIN_PASSWORD_LENGTH) {
      setPasswordError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (!fullName.trim()) {
      setError("Add your name so your team knows who you are.");
      return;
    }
    setLoading(true);
    try {
      await acceptJoin(joinToken, { full_name: fullName.trim(), password });
      // Account exists and the invite is consumed — sign straight in.
      const supabase = createClient();
      const { error: authError } = await supabase.auth.signInWithPassword({ email, password });
      if (authError) {
        // Account was created; the session just didn't start. Honest handoff.
        setError("Your account is ready, but sign-in hiccuped. Sign in with your new password.");
        setLoading(false);
        return;
      }
      router.push("/employer");
      router.refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not create your account.");
      setLoading(false);
    }
  }

  async function handleSignedInAccept(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const supabase = createClient();
    const { data, error: authError } = await supabase.auth.signInWithPassword({ email, password });
    if (authError || !data.session) {
      setError(authError?.message ?? "Could not sign in.");
      setLoading(false);
      return;
    }
    try {
      await acceptJoinSignedIn(joinToken, data.session.access_token);
      router.push("/employer");
      router.refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not accept the invite.");
      setLoading(false);
    }
  }

  return (
    <div>
      <MonoLabel className="mb-4 block">Team invite</MonoLabel>
      <h1 className="font-display text-card text-cohere-ink">
        Join {company}
      </h1>
      <p className="mt-2 text-body text-slate">
        {info.inviter_name ? `${info.inviter_name} invited you` : "You've been invited"} to{" "}
        {company}&apos;s employer workspace on SKILLED Nation
        {info.role ? ` as ${info.role === "admin" ? "an admin" : info.role === "owner" ? "an owner" : "a member"}` : ""}.
      </p>

      {info.account_exists ? (
        <form onSubmit={handleSignedInAccept} className="mt-8 space-y-5">
          <p className="rounded-md border border-hairline bg-parchment/50 p-3 text-caption text-slate">
            An account for <span className="font-medium text-cohere-ink">{email}</span> already
            exists. Sign in with it to accept the invite.
          </p>
          <div>
            <MonoLabel className="mb-1 block">Email</MonoLabel>
            <input value={email} disabled className="input-cohere opacity-70" />
          </div>
          <div>
            <MonoLabel className="mb-1 block">Password</MonoLabel>
            <PasswordInput
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          {error && (
            <p className="rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
              {error}
            </p>
          )}
          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : "Sign in and accept"}
          </button>
        </form>
      ) : (
        <form onSubmit={handleCreate} className="mt-8 space-y-5">
          <div>
            <MonoLabel className="mb-1 block">Email</MonoLabel>
            <input value={email} disabled className="input-cohere opacity-70" />
            <p className="mt-1 text-micro text-slate-muted">The invite was sent to this address.</p>
          </div>
          <div>
            <MonoLabel className="mb-1 block">Your name</MonoLabel>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="e.g. Marcus Lee"
              className="input-cohere"
              autoFocus
            />
          </div>
          <div>
            <MonoLabel className="mb-1 block">Choose a password</MonoLabel>
            <PasswordInput
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (passwordError && e.target.value.length >= MIN_PASSWORD_LENGTH) setPasswordError(null);
              }}
              autoComplete="new-password"
            />
            {passwordError && (
              <p className="mt-1 text-caption text-studio-maroon">{passwordError}</p>
            )}
          </div>
          {error && (
            <p className="rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
              {error}
            </p>
          )}
          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : `Create account and join ${company}`}
          </button>
        </form>
      )}

      <p className="mt-8 border-t border-hairline pt-6 text-micro text-slate-muted">
        By joining you get access to {company}&apos;s applications, interviews, and candidate messages.
      </p>
    </div>
  );
}
