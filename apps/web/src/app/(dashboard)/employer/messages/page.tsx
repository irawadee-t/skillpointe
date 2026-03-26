/**
 * Employer Messages — inbox showing all conversations with candidates.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { MessageSquare } from "lucide-react";

import { createClient } from "@/lib/supabase/server";

interface Conversation {
  conversation_id: string;
  other_party_name: string;
  job_title: string | null;
  last_message_at: string;
  unread_count: number;
  message_count: number;
}

async function fetchConversations(token: string): Promise<Conversation[]> {
  const API_URL =
    process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${API_URL}/conversations`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) return [];
  return res.json();
}

export default async function EmployerMessagesPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  const conversations = await fetchConversations(session.access_token);

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <Link
            href="/employer"
            className="text-sm text-zinc-400 hover:text-white inline-flex items-center gap-1 transition-colors"
          >
            ← Back to dashboard
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight text-white mt-1">Messages</h1>
          <p className="text-sm text-zinc-400 mt-0.5">
            Direct conversations with candidates
          </p>
        </div>

        {conversations.length === 0 ? (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-10 text-center">
            <MessageSquare className="w-10 h-10 text-zinc-600 mx-auto mb-3" />
            <p className="text-zinc-300 font-medium">No conversations yet</p>
            <p className="text-sm text-zinc-500 mt-1">
              Use the <strong>Message</strong> button on a candidate card to start a conversation.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {conversations.map((c) => (
              <Link
                key={c.conversation_id}
                href={`/employer/messages/${c.conversation_id}`}
                className="flex items-center justify-between bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3.5 hover:border-zinc-700 transition-all"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-white truncate">
                      {c.other_party_name}
                    </p>
                    {c.unread_count > 0 && (
                      <span className="shrink-0 inline-flex items-center justify-center w-5 h-5 rounded-full bg-cyan-500 text-black text-xs font-bold">
                        {c.unread_count}
                      </span>
                    )}
                  </div>
                  {c.job_title && (
                    <p className="text-xs text-zinc-500 mt-0.5 truncate">
                      Re: {c.job_title}
                    </p>
                  )}
                  <p className="text-xs text-zinc-500 mt-0.5">
                    {c.message_count} message{c.message_count !== 1 ? "s" : ""} ·{" "}
                    {new Date(c.last_message_at).toLocaleDateString()}
                  </p>
                </div>
                <MessageSquare className="w-4 h-4 text-zinc-600 shrink-0 ml-3" />
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
