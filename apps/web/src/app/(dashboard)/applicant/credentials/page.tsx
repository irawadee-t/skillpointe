import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { canViewApplicantPages } from "@/lib/viewAs.server";
import { ApiError } from "@/lib/api/client";
import { fetchMyProfile } from "@/lib/api/applicant";
import { getVerifyConfig, listCredentials } from "@/lib/api/credentials";
import { CredentialsClient } from "./CredentialsClient";

export default async function CredentialsPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (!(await canViewApplicantPages(session.user.app_metadata?.role))) redirect("/login");

  const token = session.access_token;

  // Ensure the applicant profile exists (credentials are keyed to it). The
  // profile check and the credentials list are independent, so they run
  // concurrently — the redirect below simply discards the in-flight list.
  let profileMissing = false;
  const credentialsPromise = listCredentials(token);
  // Verify-panel capabilities (e.g. is Checkr really configured?). On failure,
  // default to hiding optional methods — never offer a path that can't finish.
  const verifyConfigPromise = getVerifyConfig(token).catch(() => ({ checkr_enabled: false }));
  await fetchMyProfile(token).catch((e) => {
    if (e instanceof ApiError && e.status === 404) profileMissing = true;
    return null;
  });
  if (profileMissing) {
    credentialsPromise.catch(() => null); // avoid unhandled rejection
    redirect("/applicant/setup");
  }

  // Per-panel resilience (item 17): if the credentials list fails to load we
  // still render the add-form and the "how verification works" explainer, and
  // surface a small "Couldn't load your credentials" banner in the list panel.
  let credentials: Awaited<ReturnType<typeof listCredentials>> = [];
  let credentialsError: string | null = null;
  try {
    credentials = await credentialsPromise;
  } catch {
    credentialsError = "Couldn't load your credentials. Try again in a moment.";
  }
  const { checkr_enabled: checkrEnabled } = await verifyConfigPromise;

  return (
    <CredentialsClient
      initial={credentials}
      token={token}
      credentialsError={credentialsError}
      checkrEnabled={checkrEnabled}
    />
  );
}
