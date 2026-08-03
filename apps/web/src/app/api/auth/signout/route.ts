import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { createClient } from "@/lib/supabase/server";
import { VIEW_AS_COOKIE } from "@/lib/viewAs";

export async function GET() {
  const supabase = await createClient();
  await supabase.auth.signOut();

  const response = NextResponse.redirect(
    new URL("/login", process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000")
  );

  // Belt and suspenders: explicitly expire EVERY Supabase auth cookie (all
  // chunks) on the redirect response. Relying on signOut() alone left stale
  // session cookies behind in some flows, and the middleware's auto-refresh
  // could then resurrect the previous session — "sign out" that doesn't fully
  // sign out is an account-crossover risk on shared machines.
  const store = await cookies();
  for (const cookie of store.getAll()) {
    if (cookie.name.startsWith("sb-")) {
      response.cookies.set(cookie.name, "", { path: "/", maxAge: 0 });
    }
  }

  // Admin "view as applicant" debug cookie must never outlive the session that
  // created it: if it leaks into the next login (e.g. an applicant on the same
  // machine), every API call would carry X-View-As-Applicant and the backend
  // would correctly 403 non-admins — bricking their session with API errors.
  response.cookies.set(VIEW_AS_COOKIE, "", { path: "/", maxAge: 0 });

  return response;
}
