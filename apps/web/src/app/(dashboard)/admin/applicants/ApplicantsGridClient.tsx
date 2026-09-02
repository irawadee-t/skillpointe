"use client";

/**
 * ApplicantsGridClient — the directory's LIST rendering, on the DataGrid
 * operator foundation (sortable columns, roving-tabindex keyboard nav,
 * built-in empty state). The filter bar, live search, and server pagination
 * stay on the server page; rows arrive already filtered and paged.
 *
 * Row behaviors preserved from the old card list:
 *   - "View as" pill per row (audited read-only session)
 *   - "Send message" link per row (when the applicant has an email)
 *   - row activate (Enter / double-click) starts the same View-as session
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MessageSquare } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";

import { startViewAsApplicant, type AdminApplicantRow } from "@/lib/api/admin";
import { createClient } from "@/lib/supabase/client";
import { setViewAsClient } from "@/lib/viewAs";
import { DataGrid } from "@/components/ui/DataGrid";
import { ViewAsButton } from "@/components/admin/ViewAsButton";

function fullName(r: AdminApplicantRow): string {
  return [r.first_name, r.last_name].filter(Boolean).join(" ") || "Unnamed";
}

export function ApplicantsGridClient({
  rows,
  emptyMessage,
}: {
  rows: AdminApplicantRow[];
  emptyMessage: string;
}) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const activatingRef = useRef(false);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth
      .getSession()
      .then(({ data }) => setToken(data.session?.access_token ?? null));
  }, []);

  // Enter / double-click on a row opens the applicant experience as that
  // person — the same audited View-as session the row's pill starts.
  async function activate(row: AdminApplicantRow) {
    if (!token || activatingRef.current) return;
    activatingRef.current = true;
    try {
      await startViewAsApplicant(token, row.id);
      setViewAsClient({ id: row.id, name: fullName(row), email: row.email });
      router.push("/applicant");
      router.refresh();
    } catch {
      /* the per-row pill surfaces errors; row-activate fails quietly */
    } finally {
      activatingRef.current = false;
    }
  }

  const columns = useMemo<ColumnDef<AdminApplicantRow, unknown>[]>(
    () => [
      {
        id: "name",
        header: "Name",
        accessorFn: (r) => fullName(r),
        cell: (info) => (
          <span className="font-medium">{info.getValue<string>()}</span>
        ),
        meta: { skeletonWidth: 140 },
      },
      {
        id: "email",
        header: "Email",
        accessorFn: (r) => r.email ?? "—",
        cell: (info) => (
          <span className="text-slate">{info.getValue<string>()}</span>
        ),
        meta: { skeletonWidth: 160 },
      },
      {
        id: "state",
        header: "State",
        accessorFn: (r) => r.state ?? "—",
        meta: { skeletonWidth: 36 },
      },
      {
        id: "program",
        header: "Program",
        accessorFn: (r) => r.program_name_raw ?? "—",
        meta: { skeletonWidth: 180 },
      },
      {
        id: "completeness",
        header: "Completeness",
        accessorFn: (r) => r.profile_completeness,
        cell: (info) => `${info.getValue<number>()}%`,
        meta: { align: "right", skeletonWidth: 44 },
      },
      {
        id: "eligible",
        header: "Eligible",
        accessorFn: (r) => r.eligible_count,
        meta: { align: "right", skeletonWidth: 32 },
      },
      {
        id: "near_fit",
        header: "Near fit",
        accessorFn: (r) => r.near_fit_count,
        meta: { align: "right", skeletonWidth: 32 },
      },
      {
        id: "joined",
        header: "Joined",
        accessorFn: (r) => r.created_at ?? "",
        cell: (info) => {
          const v = info.getValue<string>();
          if (!v) return "—";
          const d = new Date(v);
          return Number.isNaN(d.getTime())
            ? "—"
            : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
        },
        meta: { skeletonWidth: 72 },
      },
      {
        id: "actions",
        header: "",
        enableSorting: false,
        cell: ({ row }) => (
          <span
            className="flex items-center justify-end gap-3"
            // The pill and link handle their own clicks — keep the row's
            // click/double-click handlers out of it.
            onClick={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
          >
            {row.original.email && (
              <Link
                href={`/admin/messages/compose?applicant_id=${row.original.id}`}
                className="inline-flex items-center gap-1 text-caption font-medium text-studio-maroon hover:underline"
              >
                <MessageSquare className="h-3.5 w-3.5" /> Message
              </Link>
            )}
            <ViewAsButton
              applicantId={row.original.id}
              name={fullName(row.original)}
              email={row.original.email}
            />
          </span>
        ),
        meta: { align: "right", skeletonWidth: 120 },
      },
    ],
    [],
  );

  return (
    <DataGrid<AdminApplicantRow>
      label="Applicant directory"
      data={rows}
      columns={columns}
      getRowId={(r) => r.id}
      onRowActivate={(r) => void activate(r)}
      emptyMessage={emptyMessage}
    />
  );
}
