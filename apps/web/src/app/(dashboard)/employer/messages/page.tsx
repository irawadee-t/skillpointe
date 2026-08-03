/**
 * Employer Messages — inbox showing all conversations with candidates.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { MessageSquare } from "lucide-react";

import { createClient } from "@/lib/supabase/server";
import { Card, Reveal } from "@/components/ui";
import { fetchConversations } from "@/lib/api/messages";
import { EmployerMessagesListClient } from "./EmployerMessagesListClient";

export default async function EmployerMessagesPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  const conversations = await fetchConversations(session.access_token);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Reveal>
          <Link
            href="/employer"
            className="mono-label inline-flex items-center gap-1 text-slate hover:text-ink transition-colors"
          >
            ← Back to dashboard
          </Link>
          <h1 className="font-display text-card sm:text-heading text-cohere-ink mt-3">Messages</h1>
          <p className="text-body-lg text-slate mt-3">
            Direct conversations with candidates
          </p>
        </Reveal>

        {conversations.length === 0 ? (
          <Reveal>
            <Card tone="stone" className="p-12 text-center">
              <MessageSquare className="w-10 h-10 text-cohere-green mx-auto mb-3" />
              <p className="text-body-lg font-semibold text-cohere-ink">No conversations yet</p>
              <p className="text-body text-slate mt-1">
                Use the <strong className="font-medium">Message</strong> button on a candidate card to start a conversation.
              </p>
            </Card>
          </Reveal>
        ) : (
          <EmployerMessagesListClient conversations={conversations} />
        )}
      </div>
    </main>
  );
}
