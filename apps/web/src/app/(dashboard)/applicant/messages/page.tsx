/**
 * Applicant Messages — inbox showing all conversations with employers.
 *
 * Server component: fetches an initial list, then hands off to a client
 * component (MessagesInboxClient) that polls every 15s for updates.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { ChevronLeft } from "lucide-react";

import { createClient } from "@/lib/supabase/server";
import { PageHeader } from "@/components/ui";
import { MessagesInboxClient } from "./MessagesInboxClient";

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

  const conversations: Conversation[] = await fetchConversations(session.access_token);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Link
          href="/applicant"
          className="text-body text-slate hover:text-cohere-ink inline-flex items-center gap-1 transition-colors"
        >
          <ChevronLeft className="w-4 h-4" /> Back to dashboard
        </Link>

        <PageHeader
          eyebrow="Inbox"
          title="Messages"
          lead="Direct messages from employers."
        />

        <MessagesInboxClient token={session.access_token} initial={conversations} />
      </div>
    </main>
  );
}
