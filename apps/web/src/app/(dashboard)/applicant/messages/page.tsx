/**
 * Applicant Messages — inbox showing all conversations with employers.
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

export default async function ApplicantMessagesPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "applicant") redirect("/login");

  const conversations = await fetchConversations(session.access_token);

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <Link
            href="/applicant"
            className="text-sm text-zinc-500 hover:text-zinc-900 inline-flex items-center gap-1 transition-colors"
          >
            ← Back to dashboard
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 mt-1">Messages</h1>
          <p className="text-sm text-zinc-500 mt-0.5">
            Direct messages from employers
          </p>
        </div>

        {conversations.length === 0 ? (
          <div className="bg-zinc-50 border border-zinc-200 rounded-lg p-10 text-center shadow-sm">
            <MessageSquare className="w-10 h-10 text-zinc-300 mx-auto mb-3" />
            <p className="text-zinc-700 font-medium">No messages yet</p>
            <p className="text-sm text-zinc-500 mt-1">
              Employers who match with you can send you messages here.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {conversations.map((c) => (
              <Link
                key={c.conversation_id}
                href={`/applicant/messages/${c.conversation_id}`}
                className="flex items-center justify-between bg-white border border-zinc-200 rounded-lg px-4 py-3.5 hover:border-zinc-300 transition-all shadow-sm"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-zinc-900 truncate">
                      {c.other_party_name}
                    </p>
                    {c.unread_count > 0 && (
                      <span className="shrink-0 inline-flex items-center justify-center w-5 h-5 rounded-full bg-zinc-900 text-white text-xs font-bold">
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
                <MessageSquare className="w-4 h-4 text-zinc-400 shrink-0 ml-3" />
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
