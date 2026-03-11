/**
 * Supabase Auth callback handler.
 *
 * Handles:
 * - Email confirmation links
 * - Password reset links (type=recovery)
 * - Employer invite links
 * - OAuth (future)
 *
 * After exchanging the code for a session, redirects to `next` param
 * or to the role-appropriate dashboard.
 */
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const ROLE_HOME: Record<string, string> = {
  applicant: "/applicant",
  employer: "/employer",
  admin: "/admin",
};

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next");
  const type = searchParams.get("type"); // "recovery" for password reset

  if (code) {
    const cookieStore = await cookies();

    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return cookieStore.getAll();
          },
          setAll(cookiesToSet) {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            );
          },
        },
      }
    );

    const { data, error } = await supabase.auth.exchangeCodeForSession(code);

    if (!error && data.user) {
      // Password reset flow → go to reset page
      if (type === "recovery") {
        return NextResponse.redirect(`${origin}/reset-password`);
      }

      // Explicit next param (e.g., employer invite callback)
      if (next) {
        return NextResponse.redirect(`${origin}${next}`);
      }

      // Role-based redirect
      const role = data.user.app_metadata?.role as string | undefined;
      const home = role ? (ROLE_HOME[role] ?? "/") : "/";
      return NextResponse.redirect(`${origin}${home}`);
    }
  }

  return NextResponse.redirect(`${origin}/login?error=auth_callback_failed`);
}
