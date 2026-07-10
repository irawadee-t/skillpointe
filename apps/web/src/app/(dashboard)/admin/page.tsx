import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { fetchAdminOverview } from "@/lib/api/admin";
import { AdminOverviewClient } from "./AdminOverviewClient";

export default async function AdminDashboard() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const role = session.user.app_metadata?.role;
  if (role !== "admin") redirect("/login");

  let data = null;
  let error: string | null = null;
  try {
    data = await fetchAdminOverview(session.access_token);
  } catch {
    error = "Failed to load dashboard data.";
  }

  if (error || !data) {
    return (
      <main className="py-8">
        <div className="page-shell">
          <div className="rounded-xl border border-cohere-coral/30 bg-cohere-coral/10 p-6 text-body text-cohere-ink">
            Could not load the command center. The API may be starting — refresh in a moment.
          </div>
        </div>
      </main>
    );
  }

  return <AdminOverviewClient data={data} token={session.access_token} />;
}
