/**
 * Admin messaging inbox — Applicants / Employers tabs.
 *
 * MVP scaffold: pulls the admin's conversation list (via the existing
 * conversations endpoint, filtered by counterparty role) and shows two
 * grouped inboxes so admin can find applicant threads vs employer threads
 * fast. Compose flow lives at /admin/messages/compose.
 */
import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { PageHeader, EmptyState } from "@/components/ui";
import { AdminMessagesClient } from "./AdminMessagesClient";

export default async function AdminMessagesPage({
  searchParams,
}: {
  searchParams: Promise<{ view?: "applicants" | "employers" }>;
}) {
  const sp = await searchParams;
  const view = sp.view === "employers" ? "employers" : "applicants";

  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader
          eyebrow="Inbox"
          title="Messages"
          lead="Threads with applicants and employer contacts. Compose a new message from any directory row."
          actions={
            <Link href="/admin" className="btn-secondary">← Dashboard</Link>
          }
        />

        {/* Tabs */}
        <div className="flex items-center gap-1 border-b border-hairline">
          <Link
            href="/admin/messages?view=applicants"
            className={`-mb-px border-b-2 px-4 py-2 text-[13px] font-medium transition-colors ${
              view === "applicants"
                ? "border-studio-maroon text-cohere-ink"
                : "border-transparent text-slate hover:text-cohere-ink"
            }`}
          >
            Applicants
          </Link>
          <Link
            href="/admin/messages?view=employers"
            className={`-mb-px border-b-2 px-4 py-2 text-[13px] font-medium transition-colors ${
              view === "employers"
                ? "border-studio-maroon text-cohere-ink"
                : "border-transparent text-slate hover:text-cohere-ink"
            }`}
          >
            Employers
          </Link>
        </div>

        <AdminMessagesClient token={session.access_token} view={view} />

        {/* Fallback empty explanation shown by client component if no threads */}
        <EmptyState
          title="Nothing to see yet"
          body="Threads appear here after admin sends the first message from an applicant or employer directory row."
          action={{ label: "Open applicants", href: "/admin/applicants" }}
          secondary={{ label: "Open employers", href: "/admin/employers" }}
          className="hidden data-[when-empty=true]:block"
        />
      </div>
    </main>
  );
}
