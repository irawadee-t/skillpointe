import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { searchVerifiedWorkers, SearchResponse } from "@/lib/api/verifiedWorkers";
import { VerifiedWorkersClient } from "./VerifiedWorkersClient";

const EMPTY: SearchResponse = {
  total: 0,
  page: 1,
  page_size: 25,
  workers: [],
  facets: { trades: [], credentials: [] },
};

export default async function VerifiedWorkersPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  const initial = await searchVerifiedWorkers(session.access_token).catch(() => EMPTY);

  return <VerifiedWorkersClient initial={initial} token={session.access_token} />;
}
