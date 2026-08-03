"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";
import { MonoLabel, Field } from "@/components/ui";
import { PasswordInput } from "@/components/ui/PasswordInput";

// Dev-only quick-fill credentials. The import lives inside a NODE_ENV branch so
// Next.js's dead-code elimination strips the module (and its plaintext creds)
// from production bundles. See apps/web/src/lib/dev/testAccounts.ts.
const IS_DEV = process.env.NODE_ENV === "development";
type DevAccount = { label: string; email: string; password: string };
const DEV_ACCOUNTS: readonly DevAccount[] = IS_DEV
  // eslint-disable-next-line @typescript-eslint/no-require-imports, @typescript-eslint/no-var-requires
  ? (require("@/lib/dev/testAccounts").DEV_ACCOUNTS as readonly DevAccount[])
  : [];

const ROLE_HOME: Record<string, string> = {
  applicant: "/applicant",
  employer: "/employer",
  admin: "/admin",
  institution: "/institution",
};

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  // Prefill with the applicant test account in dev — one less friction step.
  const _prefill = IS_DEV ? DEV_ACCOUNTS[1] : undefined;
  const [email, setEmail] = useState(_prefill?.email ?? "");
  const [password, setPassword] = useState(_prefill?.password ?? "");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const router = useRouter();
  const searchParams = useSearchParams();

  // Guard: if IS_DEV changes between server + client (shouldn't, but hydration
  // safety), clear the prefill.
  useEffect(() => {
    if (!IS_DEV) { setEmail(""); setPassword(""); }
  }, []);

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
        // Non-fatal
      }
    }

    const destination = nextPath ?? (role ? ROLE_HOME[role] : null) ?? "/";
    router.push(destination);
    router.refresh();
  }

  return (
    <div>
      <MonoLabel className="mb-4 block">Welcome back</MonoLabel>
      <h1 className="font-display text-card text-cohere-ink">Sign in</h1>
      <p className="mt-2 text-body text-slate">Continue to SKILLED Match.</p>

      {searchParams.get("error") === "auth_callback_failed" && (
        <p className="mt-6 rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
          Authentication failed. Please try again.
        </p>
      )}

      <form onSubmit={handleLogin} className="mt-8 space-y-5">
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

        <Field label="Password">
          <PasswordInput
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </Field>

        {error && (
          <p className="rounded-sm border border-error-red/20 bg-error-red/5 p-3 text-caption text-cohere-ink">
            {error}
          </p>
        )}

        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? "Signing in…" : "Sign in"}
        </button>

        {IS_DEV && (
          <div className="rounded-md border border-dashed border-hairline bg-parchment/50 p-3">
            <p className="text-micro font-medium uppercase tracking-[0.06em] text-slate-muted">
              Dev quick-fill
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {DEV_ACCOUNTS.map((a) => {
                // Selected = these credentials currently populate the fields.
                // Derived, not stored — typing in either field clears it.
                const isSelected = email === a.email && password === a.password;
                return (
                  <button
                    key={a.email}
                    type="button"
                    aria-pressed={isSelected}
                    onClick={() => { setEmail(a.email); setPassword(a.password); }}
                    className={
                      isSelected
                        ? "rounded-full border border-ink bg-ink px-2.5 py-1 text-[12px] font-medium text-white"
                        : "rounded-full border border-hairline bg-white px-2.5 py-1 text-[12px] text-slate transition-colors hover:border-studio-maroon hover:text-studio-maroon"
                    }
                  >
                    {a.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </form>

      <div className="mt-8 space-y-2 text-caption text-slate">
        <p>
          New applicant?{" "}
          <Link href="/signup" className="font-medium text-cohere-blue underline underline-offset-4">
            Create account
          </Link>
        </p>
        <p>
          <Link href="/forgot-password" className="text-slate-muted underline underline-offset-4 hover:text-ink">
            Forgot password?
          </Link>
        </p>
      </div>

      <p className="mt-8 border-t border-hairline pt-6 text-micro text-slate-muted">
        Employers and admins are added by invitation only. Contact SKILLED Nation if
        you need access.
      </p>
    </div>
  );
}
