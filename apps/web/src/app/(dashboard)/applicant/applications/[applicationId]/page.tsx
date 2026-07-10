import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { ApplicationDetailClient } from "./ApplicationDetailClient";

export default async function Page({ params }: { params: Promise<{ applicationId: string }> }) {
  const { applicationId } = await params;
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  return <ApplicationDetailClient token={session.access_token} applicationId={applicationId} />;
}
