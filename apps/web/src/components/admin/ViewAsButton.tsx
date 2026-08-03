"use client";

/**
 * Quiet "View as" ghost pill on admin applicant rows — starts an audited,
 * read-only view-as session and lands on the applicant dashboard.
 */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye } from "lucide-react";

import { startViewAsApplicant } from "@/lib/api/admin";
import { createClient } from "@/lib/supabase/client";
import { setViewAsClient } from "@/lib/viewAs";

export function ViewAsButton({
  applicantId,
  name,
  email,
}: {
  applicantId: string;
  name: string;
  email: string | null;
}) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => setToken(data.session?.access_token ?? null));
  }, []);

  async function start() {
    if (!token || busy) return;
    setBusy(true);
    setError(null);
    try {
      // Audited session start — works for every applicant, including
      // bulk-imported ones with no login account.
      await startViewAsApplicant(token, applicantId);
      setViewAsClient({ id: applicantId, name, email });
      router.push("/applicant");
      router.refresh();
    } catch {
      setError("Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={start}
        disabled={busy || !token}
        title="Open the applicant experience as this person (read-only debug mode)"
        className="inline-flex items-center gap-1 rounded-full border border-hairline bg-white px-2.5 py-0.5 text-caption font-medium text-slate transition-colors hover:border-cohere-ink hover:text-cohere-ink disabled:opacity-50"
      >
        <Eye className="h-3.5 w-3.5" /> {busy ? "Opening…" : "View as"}
      </button>
      {error && <span className="text-[11px] text-slate-muted">{error}</span>}
    </span>
  );
}
