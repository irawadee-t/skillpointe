import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { fetchTestApplicants } from "@/lib/api/admin";
import { TestMatchesClient } from "./TestMatchesClient";

export default async function TestMatchesPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  let applicants;
  let fetchError: string | null = null;
  try {
    applicants = await fetchTestApplicants(session.access_token);
  } catch {
    fetchError = "Failed to load applicants.";
  }

  return (
    <TestMatchesClient
      applicants={applicants ?? []}
      fetchError={fetchError}
      accessToken={session.access_token}
    />
  );
}
