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
import { canViewApplicantPages } from "@/lib/viewAs.server";
import { PageHeader } from "@/components/ui";
import { fetchConversations, type Conversation } from "@/lib/api/messages";
import { MessagesInboxClient } from "./MessagesInboxClient";

export default async function ApplicantMessagesPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (!(await canViewApplicantPages(session.user.app_metadata?.role))) redirect("/login");

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
