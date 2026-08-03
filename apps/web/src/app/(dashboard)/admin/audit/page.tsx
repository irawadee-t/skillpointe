/**
 * Admin — read-only audit-log reader. Every admin mutation writes
 * audit_logs (guardrail: all overrides auditable); this is where you read it.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { AuditLogClient } from "./AuditLogClient";

export default async function AdminAuditPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  return <AuditLogClient token={session.access_token} />;
}
