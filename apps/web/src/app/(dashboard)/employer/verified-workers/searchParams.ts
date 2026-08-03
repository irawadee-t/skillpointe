import type { SearchParams } from "@/lib/api/verifiedWorkers";

/**
 * Map URL query params to verified-worker API search params. Shared by the
 * server page (initial render honours the URL) and the client (live updates)
 * so a bookmarked/shared link restores the exact same filter state.
 */
export function toSearchParams(sp: Record<string, string | undefined>): SearchParams {
  return {
    q: sp.q || undefined,
    state: sp.state || undefined,
    trades: sp.trades || undefined,
    credential: sp.credential || undefined,
    credential_types: sp.credential_types || undefined,
    min_level: sp.min_level ? Number(sp.min_level) : undefined,
    available_by: sp.available_by || undefined,
    relocate: sp.relocate === "true" ? true : sp.relocate === "false" ? false : undefined,
    near_city: sp.near_city || undefined,
    near_state: sp.near_state || undefined,
    active_within_days: sp.active_within_days ? Number(sp.active_within_days) : undefined,
    page: sp.page ? Math.max(1, parseInt(sp.page)) : 1,
    page_size: 25,
  };
}
