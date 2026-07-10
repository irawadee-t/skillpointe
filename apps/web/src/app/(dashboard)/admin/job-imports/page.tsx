/**
 * Admin — job-import approval queue. Lists pending batches; clicking opens detail.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { ApprovalQueueClient } from "./ApprovalQueueClient";

export default async function AdminImportsPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  return <ApprovalQueueClient token={session.access_token} />;
}
