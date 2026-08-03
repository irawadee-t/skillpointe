import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { EmployerApplicationDetailClient } from "./EmployerApplicationDetailClient";

export default async function Page({ params }: { params: Promise<{ applicationId: string }> }) {
  const { applicationId } = await params;
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");
  // Admin may look, never act — employer actions are hidden in read-only mode
  // (the API independently rejects admin on employer-only mutations).
  return (
    <EmployerApplicationDetailClient
      token={session.access_token}
      applicationId={applicationId}
      readOnly={role !== "employer"}
    />
  );
}
