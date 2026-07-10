import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { ApiError } from "@/lib/api/client";
import { fetchMyProfile } from "@/lib/api/applicant";
import { listCredentials } from "@/lib/api/credentials";
import { CredentialsClient } from "./CredentialsClient";

export default async function CredentialsPage() {
  const supabase = await createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) redirect("/login");
  if (session.user.app_metadata?.role !== "applicant") redirect("/login");

  const token = session.access_token;

  // Ensure the applicant profile exists (credentials are keyed to it).
  let profileMissing = false;
  await fetchMyProfile(token).catch((e) => {
    if (e instanceof ApiError && e.status === 404) profileMissing = true;
    return null;
  });
  if (profileMissing) redirect("/applicant/setup");

  // Per-panel resilience (item 17): if the credentials list fails to load we
  // still render the add-form and the "how verification works" explainer, and
  // surface a small "Couldn't load your credentials" banner in the list panel.
  let credentials: Awaited<ReturnType<typeof listCredentials>> = [];
  let credentialsError: string | null = null;
  try {
    credentials = await listCredentials(token);
  } catch {
    credentialsError = "Couldn't load your credentials. Try again in a moment.";
  }

  return (
    <CredentialsClient
      initial={credentials}
      token={token}
      credentialsError={credentialsError}
    />
  );
}
