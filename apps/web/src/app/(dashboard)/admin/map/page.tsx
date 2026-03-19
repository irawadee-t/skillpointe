import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { fetchJobMapData } from "@/lib/api/admin";
import { JobMapClient } from "./JobMapClient";

export default async function MapPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const role = session.user.app_metadata?.role;
  if (role !== "admin") redirect("/login");

  let clusters = null;
  let error: string | null = null;
  try {
    clusters = await fetchJobMapData(session.access_token);
  } catch {
    error = "Failed to load map data.";
  }

  return <JobMapClient clusters={clusters ?? []} error={error} accessToken={session.access_token} />;
}
