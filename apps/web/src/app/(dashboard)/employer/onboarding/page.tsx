/**
 * Employer onboarding wizard — 3-step self-serve flow.
 *
 * Guardrails:
 *   - If the user already has a linked company (GET /employer/me/company returns 200),
 *     redirect to /employer.
 *   - If the API returns 404 (no company), render the wizard.
 *   - Server errors fall through to the client, which will render its own error
 *     state without blocking the flow.
 */
import { redirect } from "next/navigation";

import { fetchMyCompany } from "@/lib/api/employer";
import { ApiError } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";
import { EmployerOnboardingWizard } from "./EmployerOnboardingWizard";

export default async function EmployerOnboardingPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const role = user.app_metadata?.role;
  if (role === "admin") redirect("/admin/employers");
  if (role !== "employer") redirect("/login");

  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) redirect("/login");

  const token = session.access_token;

  // If company already exists → bounce back to dashboard.
  try {
    const company = await fetchMyCompany(token);
    if (company) redirect("/employer");
  } catch (err) {
    if (!(err instanceof ApiError && err.status === 404)) {
      // API unreachable — let the wizard render anyway; server will re-check on submit.
    }
  }

  const suggestedName =
    (user.user_metadata as Record<string, unknown> | null)?.["full_name"] as string | undefined;
  const email = user.email ?? null;

  return (
    <main className="py-10">
      <div className="mx-auto w-full max-w-2xl px-5">
        <EmployerOnboardingWizard
          token={token}
          suggestedContactName={suggestedName ?? null}
          contactEmail={email}
        />
      </div>
    </main>
  );
}
