import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { canViewApplicantPages } from "@/lib/viewAs.server";
import { ApiError } from "@/lib/api/client";
import { fetchMyProfile } from "@/lib/api/applicant";
import { listConsent } from "@/lib/api/consent";
import { ConsentClient } from "./ConsentClient";

export default async function ConsentPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (!(await canViewApplicantPages(session.user.app_metadata?.role))) redirect("/login");

  const token = session.access_token;

  let profileMissing = false;
  await fetchMyProfile(token).catch((e) => {
    if (e instanceof ApiError && e.status === 404) profileMissing = true;
    return null;
  });
  if (profileMissing) redirect("/applicant/setup");

  const settings = await listConsent(token).catch(() => []);

  return <ConsentClient initial={settings} token={token} />;
}
