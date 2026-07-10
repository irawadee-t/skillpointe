/**
 * Base API client for fetch calls to the FastAPI backend.
 *
 * Isomorphic: server components pass the Supabase access token from the session;
 * client components pass the token they received as a prop (never the secret key).
 */

// Resolve API URL. In production builds we refuse to fall back to localhost —
// a misconfigured deploy should fail loudly, not silently point at nothing.
const _API_URL =
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_API_URL
    : process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL;

if (process.env.NODE_ENV === "production" && !_API_URL) {
  throw new Error(
    "NEXT_PUBLIC_API_URL must be set in production (or API_URL on the server). " +
      "Refusing to fall back to http://localhost:8000.",
  );
}

export const API_BASE = _API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
  ) {
    super(`API ${status}: ${body}`);
  }
}

export async function apiFetch<T>(
  path: string,
  token: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
    cache: "no-store", // match data must always be fresh
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body);
  }

  return res.json() as Promise<T>;
}

/**
 * Like apiFetch but for endpoints that return no JSON body (e.g. 204 No Content).
 * Resolves on 2xx, throws ApiError otherwise.
 */
export async function apiSend(
  path: string,
  token: string,
  options?: RequestInit,
): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body);
  }
}
