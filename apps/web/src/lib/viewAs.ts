/**
 * Admin "view as applicant" debug mode — shared cookie/header plumbing.
 *
 * The mode is strictly read-only: the backend rejects any non-GET request
 * carrying the header (403 "View-as is read-only"), and only admins may send
 * it. The cookie stores the target id plus a display label so the banner can
 * render without an extra fetch.
 *
 * Isomorphic: no next/headers import here. Server components read the cookie
 * via next/headers themselves (see viewAs.server.ts); apiFetch resolves the
 * header on both sides.
 */

export const VIEW_AS_COOKIE = "sp_view_as";
export const VIEW_AS_HEADER = "X-View-As-Applicant";

export interface ViewAsTarget {
  id: string;
  name: string;
  email: string | null;
}

export function parseViewAsCookie(raw: string | undefined | null): ViewAsTarget | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(decodeURIComponent(raw)) as Partial<ViewAsTarget>;
    if (!parsed || typeof parsed.id !== "string" || !parsed.id) return null;
    return {
      id: parsed.id,
      name: typeof parsed.name === "string" ? parsed.name : "Unknown applicant",
      email: typeof parsed.email === "string" ? parsed.email : null,
    };
  } catch {
    return null;
  }
}

/** Client-side cookie read (returns null on the server). */
export function readViewAsClient(): ViewAsTarget | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${VIEW_AS_COOKIE}=`));
  return parseViewAsCookie(match ? match.slice(VIEW_AS_COOKIE.length + 1) : null);
}

/** Client-side cookie write. 8h max-age — debug sessions should not linger. */
export function setViewAsClient(target: ViewAsTarget): void {
  if (typeof document === "undefined") return;
  const value = encodeURIComponent(JSON.stringify(target));
  document.cookie = `${VIEW_AS_COOKIE}=${value}; path=/; max-age=${8 * 60 * 60}; samesite=lax`;
}

/** Client-side cookie clear (exit view-as). */
export function clearViewAsClient(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${VIEW_AS_COOKIE}=; path=/; max-age=0; samesite=lax`;
}

/* ── Exit returns to where the admin came from ──────────────────────────
 * The route the admin was on when they entered view-as, stored per-tab
 * (sessionStorage). Exit navigates back there; falls back to the chooser. */
const RETURN_KEY = "sp_view_as_return_to";

export function setViewAsReturnTo(path: string): void {
  if (typeof window === "undefined") return;
  try { window.sessionStorage.setItem(RETURN_KEY, path); } catch { /* silent */ }
}

export function readViewAsReturnTo(): string {
  if (typeof window === "undefined") return "/admin/view-as";
  try {
    const v = window.sessionStorage.getItem(RETURN_KEY);
    // Only admin routes are valid return targets.
    if (v && v.startsWith("/admin")) return v;
  } catch { /* silent */ }
  return "/admin/view-as";
}
