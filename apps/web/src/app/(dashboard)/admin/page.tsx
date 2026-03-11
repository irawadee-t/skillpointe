/**
 * Admin dashboard — Phase 2 placeholder.
 * Full admin console built in Phase 9.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export default async function AdminDashboard() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const role = user.app_metadata?.role;
  if (role !== "admin") redirect("/login");

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
            <h1 className="text-2xl font-bold">Admin Console</h1>
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

        <div className="bg-white rounded-xl shadow p-6 space-y-4">
          <p className="text-gray-600 text-sm">
            <strong>Phase 2 complete.</strong> Admin tools are added in Phase 9.
          </p>
          <ul className="mt-2 space-y-2 text-sm text-gray-500 list-disc list-inside">
            <li>User management — Phase 2 (invite-employer endpoint active)</li>
            <li>Data imports — Phase 4</li>
            <li>Taxonomy management — Phase 4</li>
            <li>Scoring/policy config — Phase 9</li>
            <li>Review queue — Phase 9</li>
            <li>Audit logs — Phase 9</li>
          </ul>
        </div>

        <div className="mt-6 bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
          <strong>Invite an employer:</strong> Use the API endpoint{" "}
          <code className="bg-amber-100 px-1 rounded">
            POST /auth/invite-employer
          </code>{" "}
          with an admin JWT to send an invite email.
        </div>
      </div>
    </main>
  );
}
