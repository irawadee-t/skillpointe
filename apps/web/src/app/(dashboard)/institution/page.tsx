import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { getInstitution, getRoster, getImports, RosterRow, ImportRun } from "@/lib/api/institution";
import { InstitutionClient } from "./InstitutionClient";

export default async function InstitutionPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "institution") redirect("/login");

  const token = session.access_token;
  const institution = await getInstitution(token).catch(() => null);
  if (!institution) redirect("/login");

  const [roster, imports] = await Promise.all([
    getRoster(token).catch((): RosterRow[] => []),
    getImports(token).catch((): ImportRun[] => []),
  ]);

  return <InstitutionClient institution={institution} initialRoster={roster} initialImports={imports} token={token} />;
}
