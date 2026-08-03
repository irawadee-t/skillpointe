import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { MatchingConfigClient, type MatchingConfigResponse } from "./MatchingConfigClient";
import { API_BASE } from "@/lib/api/client";

export default async function AdminMatchingPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  let data: MatchingConfigResponse | null = null;
  let fetchError: string | null = null;
  try {
    const res = await fetch(`${API_BASE}/admin/matching/config`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
      cache: "no-store",
    });
    if (!res.ok) throw new Error(String(res.status));
    data = (await res.json()) as MatchingConfigResponse;
  } catch {
    fetchError = "Failed to load the matching configuration.";
  }

  return (
    <MatchingConfigClient
      initial={data}
      fetchError={fetchError}
      token={session.access_token}
    />
  );
}
