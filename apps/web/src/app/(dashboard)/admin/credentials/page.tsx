/**
 * Admin — credentials. IA: the review queue (the daily work) comes FIRST;
 * CSV/SIS ingestion (the occasional task) sits collapsed below it. The
 * dashboard deep-links to #queue.
 */
import { redirect } from "next/navigation";
import { ChevronDown } from "lucide-react";

import { createClient } from "@/lib/supabase/server";
import { Breadcrumb, PageHeader } from "@/components/ui";
import { IngestClient } from "./IngestClient";
import { NormalizationClient } from "./NormalizationClient";

export default async function AdminCredentialsPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Credentials" }]} />
        <PageHeader
          eyebrow="Review"
          title="Credentials"
          lead="Workers type credential names free-form; we match each one to the standard registry. Confirm the uncertain matches first. That's the daily queue. Bulk ingestion from partner institutions lives below."
        />

        <div id="queue" className="scroll-mt-24">
          <NormalizationClient token={session.access_token} />
        </div>

        <details className="group mt-10 rounded-[10px] border border-hairline bg-white" data-tour-id="credentials-ingest">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-3.5">
            <span className="text-body font-medium text-cohere-ink">Credential ingestion (CSV / SIS)</span>
            <ChevronDown className="h-4 w-4 text-slate transition-transform group-open:rotate-180" strokeWidth={1.75} />
          </summary>
          <div className="border-t border-hairline px-5 py-4">
            <IngestClient token={session.access_token} />
          </div>
        </details>
      </div>
    </main>
  );
}
