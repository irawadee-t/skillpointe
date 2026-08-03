/**
 * Base API client for fetch calls to the FastAPI backend.
 *
 * Isomorphic: server components pass the Supabase access token from the session;
 * client components pass the token they received as a prop (never the secret key).
 */
import { readViewAsClient, VIEW_AS_HEADER } from "@/lib/viewAs";

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

/** RFC 7807 problem+json envelope the backend returns for every error. */
export interface ProblemEnvelope {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  request_id?: string | null;
  errors?: unknown;
  [key: string]: unknown;
}

/** Fallback status text when the body carries no usable detail/title. */
const STATUS_TEXT: Record<number, string> = {
  400: "That request couldn't be processed.",
  401: "Your session has expired. Sign in again.",
  403: "You don't have access to that.",
  404: "We couldn't find that.",
  409: "That conflicts with an existing change. Refresh and try again.",
  413: "That upload is too large.",
  422: "Some of the submitted information isn't valid.",
  429: "Too many requests. Wait a moment and try again.",
  500: "Something went wrong on our side. Try again in a moment.",
  502: "The service is having trouble. Try again in a moment.",
  503: "The service is temporarily unavailable. Try again in a moment.",
};

function statusText(status: number): string {
  return STATUS_TEXT[status] ?? `Something went wrong (error ${status}).`;
}

/**
 * API error with the RFC 7807 problem+json envelope parsed.
 *
 * `message` is always ONE human sentence: the envelope's `detail`, falling
 * back to its `title`, falling back to a friendly status text — never raw
 * JSON. The full envelope and `request_id` stay available for debugging
 * surfaces (see `ErrorDetails` in components/ui).
 */
export class ApiError extends Error {
  /** Parsed problem+json envelope, when the body was one. */
  public readonly problem: ProblemEnvelope | null;
  /** Correlation id for support/debugging (X-Request-ID). */
  public readonly requestId: string | null;

  constructor(
    public readonly status: number,
    public readonly body: string,
  ) {
    let problem: ProblemEnvelope | null = null;
    try {
      const parsed: unknown = JSON.parse(body);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        problem = parsed as ProblemEnvelope;
      }
    } catch {
      // Not JSON — plain-text body (proxy error page etc.); fall through.
    }
    const detail =
      typeof problem?.detail === "string" && problem.detail.trim()
        ? problem.detail.trim()
        : null;
    // `title` is machine-readable ("bad_request") — humanize the underscores.
    const title =
      typeof problem?.title === "string" && problem.title.trim()
        ? problem.title.trim().replace(/_/g, " ")
        : null;
    super(detail ?? title ?? statusText(status));
    this.problem = problem;
    this.requestId =
      typeof problem?.request_id === "string" ? problem.request_id : null;
  }
}

/**
 * Admin "view as applicant" debug mode: when the sp_view_as cookie is set,
 * every API call carries X-View-As-Applicant so /applicant/me/* endpoints
 * resolve the chosen applicant. The backend enforces admin-only + read-only —
 * for normal sessions (no cookie) this returns {} and nothing changes.
 */
async function viewAsHeaders(): Promise<Record<string, string>> {
  try {
    if (typeof window === "undefined") {
      // Server component — read the incoming request's cookies.
      const { cookies } = await import("next/headers");
      const { parseViewAsCookie, VIEW_AS_COOKIE } = await import("@/lib/viewAs");
      const store = await cookies();
      const target = parseViewAsCookie(store.get(VIEW_AS_COOKIE)?.value);
      return target ? { [VIEW_AS_HEADER]: target.id } : {};
    }
    const target = readViewAsClient();
    return target ? { [VIEW_AS_HEADER]: target.id } : {};
  } catch {
    // cookies() throws outside a request scope (e.g. build-time) — no header.
    return {};
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
      ...(await viewAsHeaders()),
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
      ...(await viewAsHeaders()),
      ...(options?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body);
  }
}
