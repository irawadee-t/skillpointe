/**
 * Applicant Planning Chat — Session Detail
 *
 * Shows full chat message history + input for sending new messages.
 * Server component for initial load; ChatClient handles real-time interaction.
 */
import Link from "next/link";
import { redirect, notFound } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { canViewApplicantPages } from "@/lib/viewAs.server";
import { ChatClient } from "@/components/chat/ChatClient";

interface Message {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

interface SessionDetail {
  session_id: string;
  title: string | null;
  created_at: string;
  is_active: boolean;
  messages: Message[];
  suggested_questions?: string[];
}

async function fetchSession(sessionId: string, token: string): Promise<SessionDetail | null> {
  const API_URL =
    process.env.API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000";
  const res = await fetch(`${API_URL}/applicant/me/chat/sessions/${sessionId}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export default async function ChatSessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;

  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");
  if (!(await canViewApplicantPages(session.user.app_metadata?.role))) redirect("/login");

  let chatSession: SessionDetail | null;
  try {
    chatSession = await fetchSession(sessionId, session.access_token);
  } catch {
    return (
      <main className="py-8">
        <div className="mx-auto w-full max-w-3xl px-5 bg-error-red/[0.06] border border-error-red/30 rounded-md p-5 text-body text-cohere-ink">
          <strong>Could not reach the API.</strong> Please refresh in a moment.
        </div>
      </main>
    );
  }

  if (!chatSession) notFound();

  return (
    <main className="flex h-[calc(100svh-3.5rem)] flex-col md:h-[calc(100svh-4rem)]">
      {/* Compact conversation header — one quiet line, the room's title. */}
      <header className="border-b border-hairline">
        <div className="mx-auto flex w-full max-w-[46rem] items-center gap-3 px-5 py-3">
          <Link
            href="/applicant/chat"
            aria-label="Back to chats"
            className="-ml-1 rounded-md p-1 text-slate transition-colors hover:text-cohere-ink"
          >
            ←
          </Link>
          <h1 className="min-w-0 truncate text-[1.0625rem] font-medium text-cohere-ink">
            {chatSession.title || "Planning chat"}
          </h1>
        </div>
      </header>

      {/* The conversation owns the rest of the viewport. */}
      <ChatClient
        sessionId={sessionId}
        initialMessages={chatSession.messages}
        isActive={chatSession.is_active}
        token={session.access_token}
        suggestedQuestions={chatSession.suggested_questions ?? []}
      />
    </main>
  );
}
