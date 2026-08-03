"use client";

/**
 * VizMarketHarness — client harness for /dev/viz-market.
 *
 * Sections:
 *   1. SupplyDemandBars   — national diverging bars (live or snapshot)
 *   2. ScoreHistogram     — 132k-score Canvas histogram (live or snapshot)
 *   3. SupplyDemandMap    — two-sided map + cross-filtered companion panel
 *   4. DataGrid           — operator grid against the REAL /admin/applicants
 *                           directory (337 rows) — the integration blueprint
 *                           for the admin/employer directories.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api/client";
import type { AdminApplicantList, AdminApplicantRow } from "@/lib/api/admin";
import { statusChipClass } from "@/components/ui/statusTones";
import { DataGrid } from "@/components/ui/DataGrid";
import type { ColumnDef } from "@tanstack/react-table";
import { SupplyDemandBars } from "@/components/viz2/SupplyDemandBars";
import { ScoreHistogram } from "@/components/viz2/ScoreHistogram";
import { SupplyDemandMap } from "@/components/viz2/SupplyDemandMap";
import {
  fetchScoreDistribution,
  fetchSupplyDemand,
  fetchSupplyDemandGeo,
  type ScoreDistributionResponse,
  type SupplyDemandGeoResponse,
  type SupplyDemandResponse,
} from "@/components/viz2/marketData";
import sample from "./sampleMarket.json";

interface MarketState {
  supply: SupplyDemandResponse;
  geo: SupplyDemandGeoResponse;
  dist: ScoreDistributionResponse;
  live: boolean;
}

const SAMPLE: MarketState = {
  supply: sample.supply_demand as SupplyDemandResponse,
  geo: sample.geo as SupplyDemandGeoResponse,
  dist: sample.score_distribution as ScoreDistributionResponse,
  live: false,
};

/** Deterministic synthetic rows for the grid when no admin session exists. */
function syntheticApplicants(n: number): AdminApplicantRow[] {
  const firsts = ["Avery", "Jordan", "Riley", "Casey", "Morgan", "Quinn", "Reese", "Skyler"];
  const lasts = ["Sample", "Example", "Placeholder", "Demo", "Fixture", "Specimen"];
  const states = ["PA", "GA", "TX", "AZ", "OH", "NY", "IN", "SC"];
  const programs = ["Welding Technology", "HVAC-R", "Electrical Systems", "Aviation Maintenance", "Automotive Technology", "Practical Nursing"];
  return Array.from({ length: n }, (_, i) => ({
    id: `synthetic-${i}`,
    first_name: firsts[i % firsts.length],
    last_name: `${lasts[i % lasts.length]} ${i + 1}`,
    email: null,
    city: null,
    state: states[(i * 3) % states.length],
    program_name_raw: programs[(i * 5) % programs.length],
    job_family_code: null,
    job_family_name: null,
    available_from: null,
    profile_completeness: (i * 37) % 101,
    willing_to_relocate: i % 3 === 0,
    eligible_count: (i * 13) % 7,
    near_fit_count: (i * 29) % 240,
  })) as unknown as AdminApplicantRow[];
}

export function VizMarketHarness({ token }: { token: string | null }) {
  // ── Market data (bars / histogram / map) ────────────────────────────────
  const [market, setMarket] = useState<MarketState | null>(null);
  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setMarket(SAMPLE);
      return;
    }
    Promise.all([
      fetchSupplyDemand(token),
      fetchSupplyDemandGeo(token),
      fetchScoreDistribution(token),
    ])
      .then(([supply, geo, dist]) => {
        if (!cancelled) setMarket({ supply, geo, dist, live: true });
      })
      .catch(() => {
        if (!cancelled) setMarket(SAMPLE);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // ── Grid data (real 337-row directory when live) ────────────────────────
  const [gridRows, setGridRows] = useState<AdminApplicantRow[] | null>(null);
  const [gridError, setGridError] = useState<string | null>(null);
  const [gridLive, setGridLive] = useState(false);
  const [activated, setActivated] = useState<string | null>(null);

  const loadGrid = useCallback(() => {
    setGridError(null);
    setGridRows(null);
    if (!token) {
      setGridRows(syntheticApplicants(120));
      return;
    }
    Promise.all([
      apiFetch<AdminApplicantList>("/admin/applicants?page=1&page_size=200", token),
      apiFetch<AdminApplicantList>("/admin/applicants?page=2&page_size=200", token),
    ])
      .then(([a, b]) => {
        setGridRows([...a.applicants, ...b.applicants]);
        setGridLive(true);
      })
      .catch(() => {
        setGridError("Could not load the applicant directory from the API.");
      });
  }, [token]);
  useEffect(loadGrid, [loadGrid]);

  const columns = useMemo<ColumnDef<AdminApplicantRow, unknown>[]>(
    () => [
      {
        id: "name",
        header: "Name",
        accessorFn: (r) =>
          `${r.first_name ?? ""} ${r.last_name ?? ""}`.trim() || "—",
        cell: (info) => (
          <span className="font-medium">{info.getValue<string>()}</span>
        ),
        meta: { skeletonWidth: 140 },
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
    ],
    [],
  );

  const sourceChip = (live: boolean) => (
    <span className={statusChipClass(live ? "positive" : "neutral")}>
      {live ? "Live data" : "Sample snapshot — sign in as admin for live"}
    </span>
  );

  return (
    <main className="min-h-screen bg-canvas py-10">
      <div className="mx-auto max-w-container px-4 sm:px-6">
        <h1 className="font-display text-heading text-cohere-ink">
          Marketplace viz harness
        </h1>
        <p className="mt-1 max-w-prose text-body text-slate">
          Dev-only proving ground for the supply/demand pieces, the score
          histogram, and the operator DataGrid. Nothing here is mounted in the
          product — the integration pass wires these into admin surfaces.
        </p>

        {/* 1 — Diverging bars */}
        <section className="mt-10">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-feature text-cohere-ink">
              Supply vs demand by trade
            </h2>
            {market ? sourceChip(market.live) : null}
          </div>
          <div className="mt-4 rounded-[10px] border border-hairline bg-white p-6">
            {market ? (
              <SupplyDemandBars families={market.supply.families} />
            ) : (
              <p className="text-caption text-slate-muted">Loading…</p>
            )}
          </div>
        </section>

        {/* 2 — Score histogram */}
        <section className="mt-10">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-feature text-cohere-ink">
              Match-quality distribution
            </h2>
            {market ? sourceChip(market.live) : null}
          </div>
          <div className="mt-4 rounded-[10px] border border-hairline bg-white p-6">
            {market ? (
              <ScoreHistogram data={market.dist} />
            ) : (
              <p className="text-caption text-slate-muted">Loading…</p>
            )}
          </div>
        </section>

        {/* 3 — Two-sided map with cross-filter */}
        <section className="mt-10">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-feature text-cohere-ink">
              Where the market is lopsided
            </h2>
            {market ? sourceChip(market.live) : null}
          </div>
          <div className="mt-4 rounded-[10px] border border-hairline bg-white p-6">
            {market ? (
              <SupplyDemandMap
                clusters={market.geo.clusters}
                families={market.supply.families}
              />
            ) : (
              <p className="text-caption text-slate-muted">Loading…</p>
            )}
          </div>
        </section>

        {/* 4 — DataGrid proof against the real directory */}
        <section className="mt-10">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-feature text-cohere-ink">
              Operator grid — applicant directory
            </h2>
            {gridRows ? (
              <span
                className={statusChipClass(gridLive ? "positive" : "neutral")}
              >
                {gridLive
                  ? `Live — ${gridRows.length} applicants`
                  : "Synthetic sample rows (no admin session)"}
              </span>
            ) : null}
          </div>
          <p className="mt-1 max-w-prose text-caption text-slate">
            Sorting (click headers), keyboard navigation (Tab into the grid,
            arrows / Home / End, Enter to open, Space to select), shift-click
            range selection, and virtualization above 60 rows.
          </p>
          {activated ? (
            <p className="mt-2 text-caption text-slate">
              Last activated row:{" "}
              <span className="font-medium text-cohere-ink">{activated}</span>
            </p>
          ) : null}
          <DataGrid<AdminApplicantRow>
            className="mt-4"
            label="Applicant directory"
            data={gridRows ?? []}
            columns={columns}
            getRowId={(r) => r.id}
            loading={gridRows === null && !gridError}
            error={gridError}
            onRetry={loadGrid}
            enableSelection
            initialSorting={[{ id: "near_fit", desc: true }]}
            onRowActivate={(r) =>
              setActivated(
                `${r.first_name ?? ""} ${r.last_name ?? ""}`.trim() || r.id,
              )
            }
            bulkActions={(selected, clear) => (
              <button
                type="button"
                className="rounded-full border border-hairline bg-white px-3 py-1 text-caption text-cohere-ink transition-colors duration-200 hover:border-ink"
                onClick={() => {
                  const names = selected
                    .map((r) =>
                      `${r.first_name ?? ""} ${r.last_name ?? ""}`.trim(),
                    )
                    .join(", ");
                  void navigator.clipboard?.writeText(names);
                  clear();
                }}
              >
                Copy names
              </button>
            )}
            emptyMessage="No applicants match."
          />
        </section>
      </div>
    </main>
  );
}
