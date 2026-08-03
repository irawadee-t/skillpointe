/**
 * Admin — message compose entry point.
 *
 * Platform-initiated DMs (admin → arbitrary user) are not part of the
 * messaging model yet: conversations are created from an applicant or
 * employer context so every thread has a real counterparty record. This
 * page says so honestly and routes the admin to those surfaces instead of
 * pretending a compose form works.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { MessageSquare } from "lucide-react";

import { createClient } from "@/lib/supabase/server";
import { Breadcrumb, PageHeader } from "@/components/ui";

export default async function ComposeMessagePage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb
          items={[
            { label: "Admin", href: "/admin" },
            { label: "Messages", href: "/admin/messages" },
            { label: "New message" },
          ]}
        />
        <PageHeader
          eyebrow="Inbox"
          title="Start a conversation"
          lead="Conversations start from a person, not a blank form. Open an applicant or employer and message them from there. The thread then appears in this inbox."
        />
        <div className="rounded-[10px] border border-hairline bg-white p-8 text-center">
          <MessageSquare className="mx-auto h-8 w-8 text-slate-muted" strokeWidth={1.5} aria-hidden />
          <p className="mt-3 text-body text-cohere-ink">Pick who you want to reach:</p>
          <div className="mt-4 flex items-center justify-center gap-3">
            <Link href="/admin/applicants" className="btn-pill-outline">Browse applicants</Link>
            <Link href="/admin/employers" className="btn-pill-outline">Browse employers</Link>
          </div>
          <p className="mt-4 text-caption text-slate">
            Existing threads live in{" "}
            <Link href="/admin/messages" className="underline hover:text-cohere-ink">Messages</Link>.
          </p>
        </div>
      </div>
    </main>
  );
}
