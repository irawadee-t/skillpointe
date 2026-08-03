"use client";

/**
 * Full-page "choose an applicant" state for admin view-as debug mode.
 *
 * Rendered by /admin/view-as (the sidebar entry point) and reached
 * automatically whenever an admin lands on any /applicant/* page without an
 * active view-as session. Type-ahead over every applicant (including
 * bulk-imported scholars with no login); selection starts an audited,
 * read-only session and lands on the applicant dashboard.
 */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { fetchAdminApplicants, startViewAsApplicant } from "@/lib/api/admin";
import { createClient } from "@/lib/supabase/client";
import { setViewAsClient, setViewAsReturnTo } from "@/lib/viewAs";
import { TypeaheadInput } from "@/components/ui";

interface Candidate {
  id: string;
  name: string;
  email: string | null;
  location: string;
  program: string | null;
}

export function ViewAsChooser() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [switching, setSwitching] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => setToken(data.session?.access_token ?? null));
    const { data: sub } = supabase.auth.onAuthStateChange((_e, sess) =>
      setToken(sess?.access_token ?? null),
    );
    return () => sub.subscription.unsubscribe();
  }, []);

  // Headline count so the admin knows the picker spans everyone.
  useEffect(() => {
    if (!token) return;
    fetchAdminApplicants(token, { page: 1 })
      .then((d) => setTotal(d.total))
      .catch(() => setTotal(null));
  }, [token]);

  async function pick(c: Candidate) {
    if (!token || switching) return;
    setSwitching(c.id);
    setNotice(null);
    try {
      // Audited session start — one audit_logs row. Works for every applicant,
      // including imported scholars with no login account.
      await startViewAsApplicant(token, c.id);
      setViewAsClient({ id: c.id, name: c.name, email: c.email });
      // Exit returns here (or wherever the referrer admin page was).
      setViewAsReturnTo(document.referrer && new URL(document.referrer).pathname.startsWith("/admin")
        ? new URL(document.referrer).pathname
        : "/admin/view-as");
      router.push("/applicant");
      router.refresh();
    } catch {
      setNotice("Could not start view-as for that applicant. Try again.");
      setSwitching(null);
    }
  }

  return (
    <div className="max-w-xl">
      <TypeaheadInput<Candidate>
        // useTypeahead only refetches on query change — remount once the auth
        // token arrives so the initial (empty-query) list isn't stuck empty.
        key={token ?? "no-token"}
        ariaLabel="Choose an applicant to view as"
        placeholder={
          total !== null ? `Search all ${total} applicants…` : "Search applicants by name, email, city…"
        }
        autoFocus
        minChars={0}
        emptyLabel="No applicants match that search."
        fetch={async (q) => {
          if (!token) return [];
          const data = await fetchAdminApplicants(token, { q: q || undefined, page: 1 });
          return data.applicants.slice(0, 8).map((a) => ({
            id: a.id,
            name: [a.first_name, a.last_name].filter(Boolean).join(" ") || "Unnamed",
            email: a.email,
            location: [a.city, a.state].filter(Boolean).join(", "),
            program: a.program_name_raw,
          }));
        }}
        getKey={(c) => c.id}
        getLabel={(c) => c.name}
        onSelect={pick}
        renderResult={(c) => (
          <span className="min-w-0">
            <span className="block truncate text-caption font-medium text-cohere-ink">
              {c.name}
              {switching === c.id ? " · opening…" : ""}
            </span>
            <span className="block truncate text-[11px] text-slate">
              {[c.email, c.location, c.program].filter(Boolean).join(" · ") || "No contact info"}
            </span>
          </span>
        )}
      />
      {notice && <p className="mt-2 text-caption text-studio-maroon">{notice}</p>}
      <p className="mt-3 text-caption text-slate">
        Sessions are read-only and audited. You can browse, but nothing you do is saved to the
        applicant&apos;s record. Use Exit in the banner to return to the admin console.
      </p>
    </div>
  );
}
