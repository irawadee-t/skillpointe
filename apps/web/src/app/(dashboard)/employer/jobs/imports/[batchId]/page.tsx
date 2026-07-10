/**
 * Employer — single import batch detail. Shows rows, status, reviewer note.
 * Draft batches remain editable; submitted/rejected are read-only.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { BatchDetailClient } from "./BatchDetailClient";

export default async function EmployerBatchDetailPage({
  params,
}: { params: Promise<{ batchId: string }> }) {
  const { batchId } = await params;
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  return <BatchDetailClient token={session.access_token} batchId={batchId} />;
}
