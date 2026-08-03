/**
 * Admin — view as applicant (read-only debug mode).
 *
 * First-class entry point in the admin sidebar (Operations group). Also the
 * landing spot when an admin hits any /applicant/* page without an active
 * view-as session (see canViewApplicantPages in lib/viewAs.server.ts).
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { Breadcrumb, PageHeader, Reveal } from "@/components/ui";
import { ViewAsChooser } from "@/components/admin/ViewAsChooser";

export default async function AdminViewAsPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "View as applicant" }]} />
        <PageHeader
          eyebrow="Operations"
          title="View as applicant"
          lead="Debug view: pick any applicant to see the app exactly as their data renders it: dashboard, matches, and profile come straight from their computed records."
        />
        <Reveal>
          <ViewAsChooser />
        </Reveal>
      </div>
    </main>
  );
}
