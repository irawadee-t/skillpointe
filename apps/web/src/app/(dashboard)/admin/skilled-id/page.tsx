import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { listPartners, Partner } from "@/lib/api/skilledIdAdmin";
import { SkilledIdConsole } from "./SkilledIdConsole";

export default async function SkilledIdAdminPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "admin") redirect("/login");

  const partners: Partner[] = await listPartners(session.access_token).catch(() => []);

  return <SkilledIdConsole initial={partners} token={session.access_token} />;
}
