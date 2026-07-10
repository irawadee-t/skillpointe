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
  return <EmployerApplicationDetailClient token={session.access_token} applicationId={applicationId} />;
}
