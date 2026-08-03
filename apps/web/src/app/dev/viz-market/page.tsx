/**
 * /dev/viz-market — dev-only harness for the marketplace-analytics pieces
 * and the DataGrid operator foundation.
 *
 * Not a product surface: gated out of production builds entirely. The
 * sibling /dev/viz route (match-explanation pieces) is owned by another
 * workstream — this route stays separate so the two harnesses never race.
 *
 * With a local admin session the sections render LIVE data from the /viz
 * endpoints and /admin/applicants (the real 337-row directory). Without one,
 * the viz sections fall back to a committed snapshot of the same endpoints
 * (sampleMarket.json — aggregates only, no PII) and the grid renders
 * clearly-labeled synthetic rows.
 */
import { notFound } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { VizMarketHarness } from "./VizMarketHarness";

export const dynamic = "force-dynamic";

export default async function VizMarketDevPage() {
  if (process.env.NODE_ENV === "production") notFound();

  let token: string | null = null;
  try {
    const supabase = await createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (session && session.user.app_metadata?.role === "admin") {
      token = session.access_token;
    }
  } catch {
    // No Supabase locally — harness falls back to the committed snapshot.
  }

  return <VizMarketHarness token={token} />;
}
