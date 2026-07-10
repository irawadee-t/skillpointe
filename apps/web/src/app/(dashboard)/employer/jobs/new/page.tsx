/**
 * New job form — Phase 6.2
 *
 * Basic scaffold for creating a new job posting.
 * Server component that renders a client form.
 */
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { Reveal } from "@/components/ui";
import { NewJobFormClient } from "./NewJobFormClient";

export default async function NewJobPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const role = session.user.app_metadata?.role;
  if (role !== "employer" && role !== "admin") redirect("/login");

  return (
    <main className="py-8">
      <div className="mx-auto w-full max-w-3xl px-5 space-y-6">
        <Reveal>
          <a
            href="/employer"
            className="mono-label inline-flex items-center gap-1 text-slate hover:text-ink transition-colors"
          >
            ← Back to dashboard
          </a>
          <h1 className="font-display text-card sm:text-heading text-cohere-ink mt-3">Post a new job</h1>
        </Reveal>

        <Reveal delay={0.1}>
          <NewJobFormClient token={session.access_token} />
        </Reveal>
      </div>
    </main>
  );
}
