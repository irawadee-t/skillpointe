import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { EmployerApplicationsClient } from "./EmployerApplicationsClient";

export default async function EmployerApplicationsPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");
  return <EmployerApplicationsClient token={session.access_token} isEmployer={role === "employer"} />;
}
