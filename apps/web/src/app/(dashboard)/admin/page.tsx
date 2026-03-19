import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { fetchAdminDashboard } from "@/lib/api/admin";
import { AdminDashboardClient } from "./AdminDashboardClient";

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
    data = await fetchAdminDashboard(session.access_token);
  } catch {
    error = "Failed to load dashboard data.";
  }

  return <AdminDashboardClient data={data} error={error} />;
}
