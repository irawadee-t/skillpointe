/**
 * Applicant, My applications — pipeline view.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { MyApplicationsClient } from "./MyApplicationsClient";

export default async function MyApplicationsPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if ((session.user.app_metadata?.role ?? "applicant") !== "applicant") redirect("/login");
  return <MyApplicationsClient token={session.access_token} />;
}
