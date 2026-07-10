import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { AccountSettingsClient } from "./AccountSettingsClient";

export default async function AccountSettingsPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  return <AccountSettingsClient token={session.access_token} initialEmail={session.user.email ?? ""} />;
}
