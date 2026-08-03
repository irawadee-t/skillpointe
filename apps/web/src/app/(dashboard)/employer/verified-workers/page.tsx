import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { searchVerifiedWorkers, SearchResponse } from "@/lib/api/verifiedWorkers";
import { VerifiedWorkersClient } from "./VerifiedWorkersClient";
import { toSearchParams } from "./searchParams";

const EMPTY: SearchResponse = {
  total: 0,
  page: 1,
  page_size: 25,
  workers: [],
  facets: { trades: [], credentials: [] },
};

interface PageProps {
  searchParams: Promise<Record<string, string | undefined>>;
}

export default async function VerifiedWorkersPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  // Initial render honours the URL, so a shared/bookmarked link restores the
  // exact filter state before the client takes over live updates.
  const initial = await searchVerifiedWorkers(
    session.access_token,
    toSearchParams(sp),
  ).catch(() => EMPTY);

  return <VerifiedWorkersClient initial={initial} token={session.access_token} />;
}
