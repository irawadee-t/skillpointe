/**
 * Employer — individual conversation thread.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { MessageThread } from "@/components/messages/MessageThread";
import { fetchConversation } from "@/lib/api/messages";

interface PageProps {
  params: Promise<{ conversationId: string }>;
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
      <main className="py-8">
        <div className="mx-auto w-full max-w-3xl px-5">
          <Link href="/employer/messages" className="mono-label inline-flex items-center gap-1 text-slate hover:text-ink transition-colors">
            ← Back to messages
          </Link>
          <div className="mt-6 rounded-md border border-error-red/30 bg-rose-50 p-5 text-body text-error-red">
            Conversation not found.
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="py-8">
      <div className="sticky top-0 z-30 -mx-5 border-b border-hairline bg-canvas/95 px-5 py-3 backdrop-blur">
        <div className="mx-auto w-full max-w-3xl">
          <Link
            href="/employer/messages"
            className="mono-label inline-flex items-center gap-1 text-slate hover:text-ink transition-colors"
          >
            ← Back to messages
          </Link>
        </div>
      </div>
      <div className="mx-auto w-full max-w-3xl px-5 pt-4 flex flex-col" style={{ height: "calc(100vh - 10rem)" }}>
        <div className="rounded-md border border-border-light bg-white p-5 flex flex-col flex-1 overflow-hidden">
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
