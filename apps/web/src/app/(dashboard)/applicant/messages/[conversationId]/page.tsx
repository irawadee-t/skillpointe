/**
 * Applicant — individual conversation thread.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { canViewApplicantPages } from "@/lib/viewAs.server";
import { MessageThread } from "@/components/messages/MessageThread";
import { fetchConversation } from "@/lib/api/messages";

interface PageProps {
  params: Promise<{ conversationId: string }>;
}

export default async function ApplicantConversationPage({ params }: PageProps) {
  const { conversationId } = await params;

  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (!(await canViewApplicantPages(session.user.app_metadata?.role))) redirect("/login");

  const conv = await fetchConversation(conversationId, session.access_token);
  if (!conv) {
    return (
      <main className="py-8">
        <div className="mx-auto w-full max-w-3xl px-5">
          <Link href="/applicant/messages" className="text-body text-slate hover:text-cohere-ink transition-colors">
            ← Back to messages
          </Link>
          <div className="mt-6 bg-error-red/[0.06] border border-error-red/30 rounded-md p-5 text-body text-cohere-ink">
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
