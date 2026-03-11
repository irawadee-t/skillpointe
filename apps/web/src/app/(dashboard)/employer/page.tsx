/**
 * Employer dashboard — Phase 2 placeholder.
 * Full ranked applicant views built in Phase 6.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export default async function EmployerDashboard() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const role = user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

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
            <h1 className="text-2xl font-bold">Employer Dashboard</h1>
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
            <strong>Phase 2 complete.</strong> Your jobs and ranked applicant
            lists will appear here in Phase 6.
          </p>
          <ul className="mt-4 space-y-2 text-sm text-gray-500 list-disc list-inside">
            <li>Job management — Phase 3</li>
            <li>Ranked applicants per job — Phase 6</li>
            <li>Applicant fit rationale — Phase 6</li>
          </ul>
        </div>
      </div>
    </main>
  );
}
