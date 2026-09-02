import type { NextConfig } from "next";

// Enterprise security headers applied to every response. CSP is conservative
// but allows what the app needs: Supabase (REST/Auth/Realtime over https + wss),
// the API origin, Google Fonts, and blob/data URIs for the WebGL canvases and
// inline SVG. Tighten connect-src/img-src to exact hosts in production.
const API_URL = process.env.NEXT_PUBLIC_API_URL || "";
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const SUPABASE_WS = SUPABASE_URL.replace(/^http/, "ws");

const csp = [
  "default-src 'self'",
  // Next.js runtime needs inline/eval; styled-jsx and inline styles need
  // 'unsafe-inline'. Consider nonce-based CSP for a stricter production posture.
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com data:",
  "img-src 'self' data: blob: https:",
  `connect-src 'self' ${API_URL} ${SUPABASE_URL} ${SUPABASE_WS}`.replace(/\s+/g, " ").trim(),
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(self), microphone=(), geolocation=(self), payment=()" },
  { key: "X-DNS-Prefetch-Control", value: "on" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false, // don't advertise the framework
  experimental: {
    // Next 15 defaults the client router cache to 0s for dynamic pages, so
    // every sidebar tab flip refetches the whole page. 30s makes back-and-forth
    // navigation instant from cache. Staleness is acceptable here: the live
    // surfaces (DM inboxes, admin badges) poll client-side on their own timers
    // regardless of the router cache, and match/analytics data changes on
    // scoring-run cadence, not seconds.
    staleTimes: {
      // 3 minutes: flipping between sidebar tabs re-uses the cached page
      // instead of a full SSR round trip. The live surfaces (DM inboxes,
      // admin badges) poll client-side regardless, and directory/analytics
      // data changes on sync cadence, not seconds.
      dynamic: 180,
    },
  },
  // Optional override so `next build` / `next start` can run against a
  // separate output dir while `next dev` owns .next (they corrupt each other's
  // caches when sharing it). Defaults to .next — no behavior change normally.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
