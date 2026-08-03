/**
 * Employer — list of their own import batches with status badges.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { MyBatchesClient } from "./MyBatchesClient";

interface PageProps {
  searchParams: Promise<{ submitted?: string; count?: string }>;
}

export default async function EmployerMyBatchesPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  const submittedCount = Number(sp.count);
  return (
    <MyBatchesClient
      token={session.access_token}
      submittedBatchId={sp.submitted || null}
      submittedCount={Number.isFinite(submittedCount) && submittedCount > 0 ? submittedCount : null}
    />
  );
}
