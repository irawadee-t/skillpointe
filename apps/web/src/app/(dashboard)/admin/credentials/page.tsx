import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { IngestClient } from "./IngestClient";

export default async function AdminCredentialsPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  return <IngestClient token={session.access_token} />;
}
