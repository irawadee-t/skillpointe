import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { canViewApplicantPages } from "@/lib/viewAs.server";
import { ApiError } from "@/lib/api/client";
import { fetchMyProfile } from "@/lib/api/applicant";
import { listCredentials } from "@/lib/api/credentials";
import { getSummary, SummaryOut } from "@/lib/api/resume";
import { listResumeUploads, ResumeUpload } from "@/lib/api/robustness";
import { ResumeClient } from "./ResumeClient";

export default async function ResumePage() {
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

  const [summary, credentials, uploads] = await Promise.all([
    getSummary(token).catch((): SummaryOut => ({ summary: null })),
    listCredentials(token).catch(() => []),
    listResumeUploads(token).catch((): ResumeUpload[] => []),
  ]);
  const verifiedCount = credentials.filter((c) => c.verification_level >= 1).length;
  const latestUpload = uploads[0] ?? null;

  return (
    <ResumeClient
      initial={summary}
      token={token}
      verifiedCount={verifiedCount}
      latestUpload={latestUpload}
    />
  );
}
