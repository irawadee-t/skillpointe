/**
 * Employer — individual conversation thread.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { MessageThread } from "@/components/messages/MessageThread";

interface PageProps {
  params: Promise<{ conversationId: string }>;
}

async function fetchConversation(id: string, token: string) {
  const API_URL =
    process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${API_URL}/conversations/${id}/messages`, {
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

export default async function EmployerConversationPage({ params }: PageProps) {
  const { conversationId } = await params;

  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  const conv = await fetchConversation(conversationId, session.access_token);
  if (!conv) {
    return (
      <main className="p-6 md:p-8">
        <div className="max-w-5xl mx-auto">
          <Link href="/employer/messages" className="text-sm text-zinc-400 hover:text-white transition-colors">
            ← Back to messages
          </Link>
          <div className="mt-6 bg-rose-500/10 border border-rose-500/30 rounded-lg p-5 text-sm text-rose-400">
            Conversation not found.
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="p-6 md:p-8">
      <div className="max-w-5xl mx-auto flex flex-col" style={{ height: "calc(100vh - 10rem)" }}>
        <Link
          href="/employer/messages"
          className="text-sm text-zinc-400 hover:text-white inline-flex items-center gap-1 mb-4 shrink-0 transition-colors"
        >
          ← Back to messages
        </Link>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 flex flex-col flex-1 overflow-hidden">
          <MessageThread
            conversationId={conversationId}
            otherPartyName={conv.other_party_name}
            jobTitle={conv.job_title}
            token={session.access_token}
            myRole="employer"
          />
        </div>
      </div>
    </main>
  );
}
