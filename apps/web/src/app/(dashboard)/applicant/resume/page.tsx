import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { ApiError } from "@/lib/api/client";
import { fetchMyProfile } from "@/lib/api/applicant";
import { listCredentials } from "@/lib/api/credentials";
import { getSummary, SummaryOut } from "@/lib/api/resume";
import { ResumeClient } from "./ResumeClient";

export default async function ResumePage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "applicant") redirect("/login");

  const token = session.access_token;

  let profileMissing = false;
  await fetchMyProfile(token).catch((e) => {
    if (e instanceof ApiError && e.status === 404) profileMissing = true;
    return null;
  });
  if (profileMissing) redirect("/applicant/setup");

  const [summary, credentials] = await Promise.all([
    getSummary(token).catch((): SummaryOut => ({ summary: null })),
    listCredentials(token).catch(() => []),
  ]);
  const verifiedCount = credentials.filter((c) => c.verification_level >= 1).length;

  return <ResumeClient initial={summary} token={token} verifiedCount={verifiedCount} />;
}
