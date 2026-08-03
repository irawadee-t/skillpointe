/**
 * Suggestion sources for the shared as-you-type dropdown (SearchSuggestField /
 * SearchWithSuggestions). One preset per surface, each backed by a
 * role-guarded API endpoint whose predicates mirror that surface's list
 * filter — picking a suggestion narrows the list exactly as typing it would.
 *
 * Presets are STRINGS so server components can pass them to the client field
 * (functions don't cross the server/client boundary).
 */

export interface SuggestionItem {
  /** Entity group — drives the group header and (optionally) which filter param a pick applies to. */
  kind: string;
  /** Display text; by default also the text applied to the filter on pick. */
  label: string;
  sublabel?: string | null;
}

export type SuggestPreset =
  | "admin-jobs"
  | "admin-applicants"
  | "admin-employers"
  | "verified-workers"
  | "jobs-browse";

/** Group headers, in display order per kind. */
export const SUGGEST_GROUP_LABELS: Record<string, string> = {
  job: "Jobs",
  employer: "Employers",
  trade: "Trades",
  credential: "Credentials",
  applicant: "Applicants",
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface SuggestRow {
  kind: string;
  label: string;
  sublabel?: string | null;
}

async function getJson<T>(path: string, token: string, signal: AbortSignal): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  });
  if (!res.ok) throw new Error(`Suggestions failed (${res.status})`);
  return res.json() as Promise<T>;
}

/** Combined /admin/search rows (label + subtitle) → dropdown items. */
interface AdminSearchRow {
  id: string;
  label: string;
  subtitle: string | null;
}

export async function fetchSuggestionsFor(
  preset: SuggestPreset,
  q: string,
  token: string,
  signal: AbortSignal,
): Promise<SuggestionItem[]> {
  const query = encodeURIComponent(q);

  if (preset === "admin-jobs") {
    const data = await getJson<{ suggestions: SuggestRow[] }>(
      `/admin/jobs/suggest?q=${query}`, token, signal,
    );
    return data.suggestions;
  }

  if (preset === "verified-workers") {
    const data = await getJson<{ suggestions: SuggestRow[] }>(
      `/employer/me/verified-workers/suggest?q=${query}`, token, signal,
    );
    return data.suggestions;
  }

  if (preset === "jobs-browse") {
    const data = await getJson<{ suggestions: SuggestRow[] }>(
      `/jobs/suggest?q=${query}`, token, signal,
    );
    return data.suggestions;
  }

  // Admin directories reuse the combined admin search, one group each.
  const data = await getJson<{ applicants?: AdminSearchRow[]; employers?: AdminSearchRow[] }>(
    `/admin/search?q=${query}&limit=8`, token, signal,
  );
  if (preset === "admin-applicants") {
    return (data.applicants ?? []).map((r) => ({
      kind: "applicant",
      label: r.label,
      sublabel: r.subtitle,
    }));
  }
  return (data.employers ?? []).map((r) => ({
    kind: "employer",
    label: r.label,
    sublabel: r.subtitle,
  }));
}
