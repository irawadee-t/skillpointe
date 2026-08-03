/**
 * Dev-only route warmup — pre-compiles the dashboard routes so the human
 * never pays the first-visit compile cost.
 *
 * Why: in `next dev`, each route compiles on demand the first time it is
 * requested (0.6–2.6s per route with webpack). loading.tsx cannot help — the
 * loading file itself compiles WITH the route. Production builds eliminate
 * this entirely; this script eliminates it in dev by visiting every main
 * route headlessly right after the server boots.
 *
 * Auth: the middleware redirects unauthenticated requests before the route
 * module ever loads (a 307 compiles nothing), so the script signs in as the
 * seeded test users (scripts/seed_test_users.py — Test1234!) via
 * @supabase/ssr with an in-memory cookie jar, then requests each role's
 * routes with real session cookies. If sign-in fails (no seeded users, no
 * Supabase running), it exits quietly — warmup is best-effort by design.
 *
 * Wired into `pnpm dev` (backgrounded); also runnable standalone:
 *   node scripts/warm-dev-routes.mjs [--base http://localhost:3000]
 */
import { readFileSync } from "node:fs";
import { createServerClient } from "@supabase/ssr";

const BASE =
  process.argv.includes("--base")
    ? process.argv[process.argv.indexOf("--base") + 1]
    : `http://localhost:${process.env.PORT ?? 3000}`;

const PASSWORD = "Test1234!";
const ROLE_ROUTES = {
  "applicant@test.local": [
    "/applicant",
    "/applicant/matches",
    "/applicant/jobs",
    "/applicant/applications",
    "/applicant/messages",
    "/applicant/chat",
    "/applicant/credentials",
    "/applicant/profile",
    "/applicant/resume",
    "/applicant/consent",
    "/account/settings",
  ],
  "employer@test.local": [
    "/employer",
    "/employer/jobs",
    "/employer/applications",
    "/employer/messages",
    "/employer/analytics",
    "/employer/verified-workers",
  ],
  "admin@test.local": [
    "/admin",
    "/admin/applicants",
    "/admin/employers",
    "/admin/jobs",
    "/admin/map",
    "/admin/engagement",
    "/admin/messages",
    "/admin/review",
    "/admin/audit",
    "/admin/credentials",
    "/admin/job-imports",
    "/admin/career-sources",
    "/admin/matching",
    "/admin/foundation",
  ],
};

function readEnvLocal() {
  const url = new URL("../.env.local", import.meta.url);
  const out = {};
  try {
    for (const line of readFileSync(url, "utf8").split("\n")) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
      if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, "");
    }
  } catch {
    /* no env file — bail later */
  }
  return out;
}

async function waitForServer(timeoutMs = 90_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${BASE}/login`, { redirect: "manual" });
      if (res.status < 500) return true;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
  return false;
}

/** Sign in with an in-memory cookie jar; returns a Cookie header string. */
async function signIn(supabaseUrl, anonKey, email) {
  const jar = new Map();
  const supabase = createServerClient(supabaseUrl, anonKey, {
    cookies: {
      getAll: () => [...jar].map(([name, value]) => ({ name, value })),
      setAll: (cookies) => cookies.forEach((c) => jar.set(c.name, c.value)),
    },
  });
  const { error } = await supabase.auth.signInWithPassword({
    email,
    password: PASSWORD,
  });
  if (error) return null;
  return [...jar].map(([n, v]) => `${n}=${v}`).join("; ");
}

async function main() {
  const env = readEnvLocal();
  const supabaseUrl = env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!supabaseUrl || !anonKey) return; // nothing to do without local env

  if (!(await waitForServer())) return;

  let warmed = 0;
  const t0 = Date.now();
  for (const [email, routes] of Object.entries(ROLE_ROUTES)) {
    const cookie = await signIn(supabaseUrl, anonKey, email);
    if (!cookie) continue; // test user not seeded — skip this role quietly
    for (const route of routes) {
      try {
        await fetch(`${BASE}${route}`, {
          headers: { Cookie: cookie },
          redirect: "manual",
        });
        warmed += 1;
      } catch {
        /* best-effort */
      }
    }
  }
  if (warmed > 0) {
    console.log(
      `[warm] pre-compiled ${warmed} routes in ${((Date.now() - t0) / 1000).toFixed(1)}s — first clicks are instant`,
    );
  }
}

main().catch(() => {});
