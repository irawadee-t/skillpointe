/**
 * Admin — the ops review feed. One prioritized queue over review_queue_items
 * (chat guardrail trips, credential ambiguity, taxonomy mismatches, broken
 * apply links, …), grouped by type, deep-linking to each resolution surface.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { ReviewFeedClient } from "./ReviewFeedClient";

export default async function AdminReviewPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  return <ReviewFeedClient token={session.access_token} />;
}
