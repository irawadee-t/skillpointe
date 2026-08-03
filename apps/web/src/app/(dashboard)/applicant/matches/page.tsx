import { redirect } from "next/navigation";
import { fetchMyMatches } from "@/lib/api/applicant";
import { createClient } from "@/lib/supabase/server";
import { canViewApplicantPages } from "@/lib/viewAs.server";
import { MatchesClient } from "./MatchesClient";

export default async function MatchesPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");
  if (!(await canViewApplicantPages(session.user.app_metadata?.role))) redirect("/login");

  const token = session.access_token;
  let matches;
  let fetchError: string | null = null;
  try {
    matches = await fetchMyMatches(token);
  } catch {
    fetchError = "Failed to load matches. Please try again or contact support.";
  }

  return (
    <MatchesClient
      data={matches ?? null}
      fetchError={fetchError}
      token={token}
    />
  );
}
