import { Suspense } from "react";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { fetchAdminOverview } from "@/lib/api/admin";
import { RouteLoading } from "@/components/ui/RouteLoading";
import { AdminOverviewClient } from "./AdminOverviewClient";

export default async function AdminDashboard() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const role = session.user.app_metadata?.role;
  if (role !== "admin") redirect("/login");

  // Stream: the route paints instantly (skeleton below) while the overview
  // fetch runs — the fetch itself is unchanged.
  return (
    <Suspense fallback={<RouteLoading variant="dashboard" />}>
      <AdminOverview token={session.access_token} />
    </Suspense>
  );
}

async function AdminOverview({ token }: { token: string }) {
  let data = null;
  let error: string | null = null;
  try {
    data = await fetchAdminOverview(token);
  } catch {
    error = "Failed to load dashboard data.";
  }

  if (error || !data) {
    return (
      <main className="py-8">
        <div className="page-shell">
          <div className="rounded-xl border border-error-red/30 bg-error-red/[0.06] p-6 text-body text-cohere-ink">
            Could not load the command center. The API may be starting. Refresh in a moment.
          </div>
        </div>
      </main>
    );
  }

  return <AdminOverviewClient data={data} token={token} />;
}
