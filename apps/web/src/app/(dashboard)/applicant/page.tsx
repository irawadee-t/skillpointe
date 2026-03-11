/**
 * Applicant dashboard — Phase 2 placeholder.
 * Full ranked job views built in Phase 6.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export default async function ApplicantDashboard() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const role = user.app_metadata?.role;
  if (role !== "applicant") redirect("/login");

  async function signOut() {
    "use server";
    const supabase = await createClient();
    await supabase.auth.signOut();
    redirect("/login");
  }

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">Applicant Dashboard</h1>
            <p className="text-gray-500 text-sm mt-1">{user.email}</p>
          </div>
          <form action={signOut}>
            <button
              type="submit"
              className="text-sm text-gray-600 hover:text-red-600 underline"
            >
              Sign out
            </button>
          </form>
        </div>

        <div className="bg-white rounded-xl shadow p-6">
          <p className="text-gray-600 text-sm">
            <strong>Phase 2 complete.</strong> Your profile and ranked job
            recommendations will appear here in Phase 6.
          </p>
          <ul className="mt-4 space-y-2 text-sm text-gray-500 list-disc list-inside">
            <li>Ranked job matches — Phase 6</li>
            <li>Match explanations — Phase 6</li>
            <li>Missing requirements — Phase 6</li>
            <li>Planning chat — Phase 8</li>
          </ul>
        </div>
      </div>
    </main>
  );
}
