/**
 * Admin — single batch review. Per-row approve/reject, batch-level approve/reject buttons.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { AdminBatchClient } from "./AdminBatchClient";

export default async function AdminBatchDetailPage({
  params,
}: { params: Promise<{ batchId: string }> }) {
  const { batchId } = await params;
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  return <AdminBatchClient token={session.access_token} batchId={batchId} />;
}
