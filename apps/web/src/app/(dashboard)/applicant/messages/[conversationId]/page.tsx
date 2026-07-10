/**
 * Applicant — individual conversation thread.
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

export default async function ApplicantConversationPage({ params }: PageProps) {
  const { conversationId } = await params;

  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "applicant") redirect("/login");

  const conv = await fetchConversation(conversationId, session.access_token);
  if (!conv) {
    return (
      <main className="py-8">
        <div className="mx-auto w-full max-w-3xl px-5">
          <Link href="/applicant/messages" className="text-body text-slate hover:text-cohere-ink transition-colors">
            ← Back to messages
          </Link>
          <div className="mt-6 bg-cohere-coral/10 border border-cohere-coral-soft rounded-md p-5 text-body text-error-red">
            Conversation not found.
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="py-8">
      <div className="mx-auto w-full max-w-3xl px-5 flex flex-col" style={{ height: "calc(100vh - 10rem)" }}>
        <Link
          href="/applicant/messages"
          className="text-body text-slate hover:text-cohere-ink inline-flex items-center gap-1 mb-4 shrink-0 transition-colors"
        >
          ← Back to messages
        </Link>
        <div className="bg-white border border-border-light rounded-md p-5 flex flex-col flex-1 overflow-hidden">
          <MessageThread
            conversationId={conversationId}
            otherPartyName={conv.other_party_name}
            jobTitle={conv.job_title}
            token={session.access_token}
            myRole="applicant"
          />
        </div>
      </div>
    </main>
  );
}
