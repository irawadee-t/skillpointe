/**
 * Employer Messages — inbox showing all conversations with candidates.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { MessageSquare } from "lucide-react";

import { createClient } from "@/lib/supabase/server";
import { Card, MonoLabel, Reveal, Stagger, StaggerItem } from "@/components/ui";

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
          <Stagger className="space-y-3">
            {conversations.map((c) => (
              <StaggerItem key={c.conversation_id}>
                <Card interactive href={`/employer/messages/${c.conversation_id}`} className="flex items-center justify-between px-5 py-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-cohere-ink truncate">
                        {c.other_party_name}
                      </p>
                      {c.unread_count > 0 && (
                        <span className="shrink-0 inline-flex items-center justify-center min-w-5 h-5 px-1.5 rounded-full bg-cohere-green text-white text-micro font-bold tabular-nums">
                          {c.unread_count}
                        </span>
                      )}
                    </div>
                    {c.job_title && (
                      <p className="text-body text-slate mt-0.5 truncate">
                        Re: {c.job_title}
                      </p>
                    )}
                    <p className="text-body text-slate mt-0.5 tabular-nums">
                      {c.message_count} message{c.message_count !== 1 ? "s" : ""},{" "}
                      {new Date(c.last_message_at).toLocaleDateString()}
                    </p>
                  </div>
                  <MessageSquare className="w-4 h-4 text-slate shrink-0 ml-3" />
                </Card>
              </StaggerItem>
            ))}
          </Stagger>
        )}
      </div>
    </main>
  );
}
