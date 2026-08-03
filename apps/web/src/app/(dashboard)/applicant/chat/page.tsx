/**
 * Applicant Planning Chat — Session List
 *
 * Shows existing chat sessions and a button to start a new one.
 * Server component; creation is a client-side action via ChatStartButton.
 */
import { redirect } from "next/navigation";
import { MessageCircle } from "lucide-react";

import { createClient } from "@/lib/supabase/server";
import { canViewApplicantPages } from "@/lib/viewAs.server";
import { ChatJobPicker } from "@/components/chat/ChatJobPicker";
import { PageHeader, Card, Stagger, StaggerItem } from "@/components/ui";
import { formatRelative } from "@/lib/time";

interface SessionRow {
  session_id: string;
  title: string | null;
  created_at: string;
  message_count: number;
  is_active: boolean;
}

async function fetchSessions(token: string): Promise<SessionRow[]> {
  const API_URL =
    process.env.API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000";
  const res = await fetch(`${API_URL}/applicant/me/chat/sessions`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) return [];
  return res.json();
}

export default async function ChatListPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");
  if (!(await canViewApplicantPages(session.user.app_metadata?.role))) redirect("/login");

  const sessions = await fetchSessions(session.access_token);

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Planning"
          title="Career planning chat"
          lead="Get personalized advice based on your job matches."
          actions={
            <span data-tour-id="chat-new">
              <ChatJobPicker token={session.access_token} />
            </span>
          }
        />

        {/* Session list */}
        {sessions.length === 0 ? (
          <div className="bg-stone border border-transparent rounded-md p-12 text-center" data-tour-id="chat-sessions">
            <MessageCircle className="w-10 h-10 text-slate mx-auto mb-3" />
            <p className="text-[1.0625rem] font-medium text-cohere-ink">No conversations yet</p>
            <p className="text-body text-slate mt-1">
              Start a planning chat to get personalized career guidance based on your matches.
            </p>
            <div className="mt-6 flex justify-center">
              <ChatJobPicker
                token={session.access_token}
                triggerLabel="Start a planning chat"
              />
            </div>
          </div>
        ) : (
          <div data-tour-id="chat-sessions">
          <Stagger className="space-y-2.5">
            {sessions.map((s) => (
              <StaggerItem key={s.session_id}>
                <Card interactive href={`/applicant/chat/${s.session_id}`} className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold text-cohere-ink truncate">
                        {s.title || "Planning chat"}
                      </p>
                      <p className="text-caption text-slate mt-0.5">
                        {s.message_count} message{s.message_count !== 1 ? "s" : ""},{" "}
                        {formatRelative(s.created_at)}
                      </p>
                    </div>
                    <MessageCircle className="w-4 h-4 text-slate shrink-0 mt-0.5" />
                  </div>
                </Card>
              </StaggerItem>
            ))}
          </Stagger>
          </div>
        )}
      </div>
    </main>
  );
}
