import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { getSummary, getCohorts, Summary, Cohort } from "@/lib/api/foundation";
import { FoundationClient } from "./FoundationClient";

const EMPTY: Summary = {
  total_served: 0, placed: 0, employment_rate: null, median_wage: null,
  attainment_rate: null, median_time_to_hire_days: null,
};

export default async function FoundationPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  const token = session.access_token;
  const [summary, cohorts] = await Promise.all([
    getSummary(token).catch((): Summary => EMPTY),
    getCohorts(token, "program").catch((): Cohort[] => []),
  ]);

  return <FoundationClient summary={summary} initialCohorts={cohorts} token={token} />;
}
