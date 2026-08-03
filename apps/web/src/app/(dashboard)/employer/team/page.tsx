/**
 * Employer team — who's in the organization, with email invites.
 *
 * Server component: auth guard + token, then the client does the work.
 * Employer-only (the backend enforces the same); admin has its own console.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { TeamClient } from "./TeamClient";

export default async function EmployerTeamPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const role = user.app_metadata?.role;
  if (role === "admin") redirect("/admin/employers");
  if (role !== "employer") redirect("/login");

  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");

  return <TeamClient token={session.access_token} />;
}
