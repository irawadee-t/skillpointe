/**
 * Next.js middleware — session refresh + role-based route protection.
 *
 * Rules (from CLAUDE.md + DECISIONS.md):
 * - Applicant cannot access /employer/** or /admin/**
 * - Employer cannot access /admin/**
 * - Admin can access all protected routes
 * - Unauthenticated users are redirected to /login
 * - Authenticated users on /login or /signup are redirected to their dashboard
 *
 * IMPORTANT: Role is read from Supabase user.app_metadata.role (set by FastAPI
 * after signup). This avoids an extra DB call in middleware.
 * The FastAPI backend ALWAYS re-validates role from the DB on API requests —
 * the JWT metadata is a routing convenience only, not a security enforcement point.
 */
import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

// Routes that require authentication
const PROTECTED_PREFIXES = ["/applicant", "/employer", "/admin"];

// Auth pages — redirect away if already logged in
const AUTH_PAGES = ["/login", "/signup"];

// Role → home dashboard path
const ROLE_HOME: Record<string, string> = {
  applicant: "/applicant",
  employer: "/employer",
  admin: "/admin",
};

// Which prefixes each role may access
const ROLE_ALLOWED_PREFIXES: Record<string, string[]> = {
  applicant: ["/applicant"],
  employer: ["/employer"],
  admin: ["/applicant", "/employer", "/admin"], // admin can see all
};

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) =>
            request.cookies.set(name, value, options)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  // IMPORTANT: Do not add any logic between createServerClient and getUser().
  // See: https://supabase.com/docs/guides/auth/server-side/nextjs
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;

  const isProtected = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
  const isAuthPage = AUTH_PAGES.some((p) => pathname === p);

  // 1. No session + protected route → login
  if (!user && isProtected) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // 2. Has session + auth page → dashboard
  if (user && isAuthPage) {
    const role = user.app_metadata?.role as string | undefined;
    const home = role ? (ROLE_HOME[role] ?? "/") : "/";
    return NextResponse.redirect(new URL(home, request.url));
  }

  // 3. Has session + protected route → enforce role boundaries
  if (user && isProtected) {
    const role = user.app_metadata?.role as string | undefined;

    if (!role) {
      // Profile not yet set up — redirect to complete-signup page
      return NextResponse.redirect(new URL("/signup/complete", request.url));
    }

    const allowed = ROLE_ALLOWED_PREFIXES[role] ?? [];
    const canAccess = allowed.some((p) => pathname.startsWith(p));

    if (!canAccess) {
      const home = ROLE_HOME[role] ?? "/";
      return NextResponse.redirect(new URL(home, request.url));
    }
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    /*
     * Match all request paths except static files, images, and favicons.
     */
    "/((?!_next/static|_next/image|favicon\\.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
