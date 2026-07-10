/**
 * Employer — list of their own import batches with status badges.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { MyBatchesClient } from "./MyBatchesClient";

export default async function EmployerMyBatchesPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  return <MyBatchesClient token={session.access_token} />;
}
