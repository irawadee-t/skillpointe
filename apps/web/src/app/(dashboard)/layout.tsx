/**
 * Dashboard layout — server-side auth guard.
 *
 * Middleware handles the redirect, but this layout provides a second server-side
 * check as defense-in-depth. Never rely on middleware alone.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return <>{children}</>;
}
