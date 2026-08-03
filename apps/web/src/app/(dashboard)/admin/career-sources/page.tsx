/**
 * Admin — career-sources console. Every connected careers page with sync
 * health, plus a per-source sync activity timeline.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { CareerSourcesClient } from "./CareerSourcesClient";

export default async function AdminCareerSourcesPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  return <CareerSourcesClient token={session.access_token} />;
}
