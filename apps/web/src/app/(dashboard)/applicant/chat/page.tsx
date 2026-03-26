/**
 * Applicant Planning Chat — Session List
 *
 * Shows existing chat sessions and a button to start a new one.
 * Server component; creation is a client-side action via ChatStartButton.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { MessageCircle } from "lucide-react";

import { createClient } from "@/lib/supabase/server";
import { ChatJobPicker } from "@/components/chat/ChatJobPicker";

interface SessionRow {
  session_id: string;
  title: string | null;
  created_at: string;
  message_count: number;
  is_active: boolean;
}

async function fetchSessions(token: string): Promise<SessionRow[]> {
  const API_URL =
    process.env.API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000";
  const res = await fetch(`${API_URL}/applicant/me/chat/sessions`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) return [];
  return res.json();
}

export default async function ChatListPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "applicant") redirect("/login");

  const sessions = await fetchSessions(session.access_token);

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-spf-navy">Career Planning Chat</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Get personalised advice based on your job matches
            </p>
          </div>
          <ChatJobPicker token={session.access_token} />
        </div>

        {/* Session list */}
        {sessions.length === 0 ? (
          <div className="bg-white border border-gray-200 rounded-xl p-10 text-center">
            <MessageCircle className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-600 font-medium">No conversations yet</p>
            <p className="text-sm text-gray-400 mt-1">
              Start a planning chat to get personalised career guidance based on your matches.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {sessions.map((s) => (
              <Link
                key={s.session_id}
                href={`/applicant/chat/${s.session_id}`}
                className="block bg-white border border-gray-200 rounded-xl p-4 hover:border-gray-300 hover:shadow-sm transition-all"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-gray-900 truncate">
                      {s.title || "Planning chat"}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {s.message_count} message{s.message_count !== 1 ? "s" : ""} ·{" "}
                      {new Date(s.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <MessageCircle className="w-4 h-4 text-gray-300 shrink-0 mt-0.5" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
