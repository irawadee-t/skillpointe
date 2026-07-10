/**
 * Employer self-serve job import — wizard landing.
 * Pick a mode (URL / CSV / Manual), preview rows, submit for admin review.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { ImportClient } from "./ImportClient";

export default async function EmployerJobImportPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  return <ImportClient token={session.access_token} />;
}
