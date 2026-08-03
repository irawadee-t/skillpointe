/**
 * DM inbox fetchers shared by the applicant and employer messages routes.
 *
 * Server-component callers: uses API_URL (server-only) before the public
 * fallback, and swallows errors into empty results so the inbox renders
 * even when the API is briefly unreachable.
 */

export interface Conversation {
  conversation_id: string;
  other_party_name: string;
  job_title: string | null;
  last_message_at: string;
  unread_count: number;
  message_count: number;
}

function apiUrl(): string {
  return process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

export async function fetchConversations(token: string): Promise<Conversation[]> {
  const res = await fetch(`${apiUrl()}/conversations`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchConversation(id: string, token: string) {
  const res = await fetch(`${apiUrl()}/conversations/${id}/messages`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json() as Promise<{
    conversation_id: string;
    other_party_name: string;
    job_title: string | null;
    messages: unknown[];
  }>;
}
