/**
 * Applicant Planning Chat — Session Detail
 *
 * Shows full chat message history + input for sending new messages.
 * Server component for initial load; ChatClient handles real-time interaction.
 */
import Link from "next/link";
import { redirect, notFound } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
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
  if (session.user.app_metadata?.role !== "applicant") redirect("/login");

  let chatSession: SessionDetail | null;
  try {
    chatSession = await fetchSession(sessionId, session.access_token);
  } catch {
    return (
      <main className="p-6 md:p-8">
        <div className="max-w-5xl mx-auto bg-rose-500/10 border border-rose-500/30 rounded-lg p-5 text-sm text-rose-400">
          <strong>Could not reach the API.</strong> Please refresh in a moment.
        </div>
      </main>
    );
  }

  if (!chatSession) notFound();

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-4">
        {/* Header */}
        <div>
          <Link
            href="/applicant/chat"
            className="text-sm text-zinc-400 hover:text-white inline-flex items-center gap-1 transition-colors"
          >
            ← Back to chats
          </Link>
          <h1 className="text-xl font-semibold text-white mt-1">
            {chatSession.title || "Planning chat"}
          </h1>
        </div>

        {/* Chat interface */}
        <ChatClient
          sessionId={sessionId}
          initialMessages={chatSession.messages}
          isActive={chatSession.is_active}
          token={session.access_token}
        />
      </div>
    </main>
  );
}
