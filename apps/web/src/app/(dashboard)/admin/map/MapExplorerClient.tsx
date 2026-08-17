"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import dynamic from "next/dynamic";
import { Marker } from "react-simple-maps";
import { ExternalLink, Filter, MapPin, RefreshCw, X, AlertTriangle } from "lucide-react";
import type {
  ApplicationFlow,
  CityApplicantCluster,
  CityJobCluster,
  ClusterJob,
} from "@/lib/api/admin";
import { fetchApplicantMap, fetchApplicationFlows, fetchClusterJobs } from "@/lib/api/admin";
import {
  fetchSupplyDemand,
  fetchSupplyDemandGeo,
  type SupplyDemandGeoResponse,
  type SupplyDemandResponse,
} from "@/components/viz2/marketData";
import { Breadcrumb, MonoLabel, PageHeader } from "@/components/ui";
import { FlowArcLayer, UsMapFrame, ViewToggle } from "@/components/viz";

/** The two-sided supply/demand composite is heavy (its own map frame +
 *  companion bars) — split it out of the initial bundle; it loads only when
 *  the fourth view is toggled. */
const SupplyDemandMap = dynamic(
  () =>
    import("@/components/viz2/SupplyDemandMap").then((m) => m.SupplyDemandMap),
  { ssr: false, loading: () => <SupplyDemandSkeleton /> },
);

function SupplyDemandSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading supply and demand map" className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
      <div className="h-[280px] w-full rounded-md bg-stone/50 sm:h-[420px]" />
      <div className="min-w-0">
        <div className="h-4 w-40 rounded-full bg-stone" />
        <div className="mt-4 space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-[10px] rounded-full bg-stone" style={{ width: `${85 - i * 11}%` }} />
          ))}
        </div>
      </div>
    </div>
  );
}

interface Props {
  clusters: CityJobCluster[];
  error: string | null;
  accessToken: string;
}

type MapView = "jobs" | "workers" | "applications" | "supply";

const ACCENT = "#9d2235";

/**
 * Clean categorical palette — brand red + restrained accents so the map
 * reads as part of the site, not a rainbow overlay.
 * Order matches the legend below (most common trades first).
 */
const FAMILY_COLORS: Record<string, string> = {
  electrical:    "#9D2235", // brand maroon
  welding:       "#dc5000", // sienna orange
  hvac:          "#4a4b2f", // olive
  manufacturing: "#17171c", // ink
  automotive:    "#5c5a55", // neutral gray
  construction:  "#b8621f", // copper
  logistics:     "#2d3320", // deep forest
  aviation:      "#1863dc", // action blue
};

const DEFAULT_MARKER_COLOR = "#75726c";

function familyLabel(family: string) {
  return family.charAt(0).toUpperCase() + family.slice(1).replace(/_/g, " ");
}

function haversineMiles(aLat: number, aLng: number, bLat: number, bLng: number) {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const R = 3959; // miles
  const dLat = toRad(bLat - aLat);
  const dLng = toRad(bLng - aLng);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/** Count-weighted median distance (miles) + share of in-state flows. */
function flowInsight(flows: ApplicationFlow[]): string | null {
  const total = flows.reduce((s, f) => s + f.count, 0);
  if (total === 0) return null;

  const inState = flows.reduce((s, f) => s + (f.from.state === f.to.state ? f.count : 0), 0);
  const pct = Math.round((100 * inState) / total);

  const sorted = flows
    .map((f) => ({ d: haversineMiles(f.from.lat, f.from.lng, f.to.lat, f.to.lng), c: f.count }))
    .sort((a, b) => a.d - b.d);
  let cum = 0;
  let median = 0;
  for (const { d, c } of sorted) {
    cum += c;
    if (cum >= total / 2) {
      median = Math.round(d);
      break;
    }
  }

  if (pct >= 60) return `Most applications stay in-state (${pct}%), median ${median} mi from home.`;
  if (pct >= 40) return `Applications are split: ${pct}% stay in-state, median ${median} mi from home.`;
  return `Most applications cross state lines: only ${pct}% in-state, median ${median} mi from home.`;
}

/** "9%", or "<1%" instead of a misleading rounded "0%". */
function pctLabel(part: number, whole: number): string {
  return part > 0 && part / whole < 0.005 ? "<1%" : `${Math.round((100 * part) / whole)}%`;
}

interface TooltipState {
  x: number;
  y: number;
  lines: string[];
}

export function MapExplorerClient({ clusters, error, accessToken }: Props) {
  const [view, setView] = useState<MapView>("jobs");
  const [familyFilter, setFamilyFilter] = useState<string>("");
  const [selectedCluster, setSelectedCluster] = useState<CityJobCluster | null>(null);
  const [clusterJobs, setClusterJobs] = useState<ClusterJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [jobsError, setJobsError] = useState<string | null>(null);

  // Lazy-loaded view data, fetched once on first toggle.
  const [workers, setWorkers] = useState<CityApplicantCluster[] | null>(null);
  const [flows, setFlows] = useState<ApplicationFlow[] | null>(null);
  const [viewError, setViewError] = useState<string | null>(null);
  const [viewLoading, setViewLoading] = useState(false);

  // Supply-vs-demand view data (both endpoints), fetched once on first toggle.
  const [supply, setSupply] = useState<{
    families: SupplyDemandResponse;
    geo: SupplyDemandGeoResponse;
  } | null>(null);
  const [supplyLoading, setSupplyLoading] = useState(false);
  const [supplyError, setSupplyError] = useState<string | null>(null);

  const loadSupply = useCallback(() => {
    setSupplyLoading(true);
    setSupplyError(null);
    Promise.all([fetchSupplyDemand(accessToken), fetchSupplyDemandGeo(accessToken)])
      .then(([families, geo]) => setSupply({ families, geo }))
      .catch((err) =>
        setSupplyError(err instanceof Error ? err.message : "Request failed"),
      )
      .finally(() => setSupplyLoading(false));
  }, [accessToken]);

  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const mapCardRef = useRef<HTMLDivElement | null>(null);

  const filteredClusters = useMemo(
    () => (familyFilter ? clusters.filter((c) => c.families.includes(familyFilter)) : clusters),
    [clusters, familyFilter],
  );

  const allFamilies = useMemo(
    () => [...new Set(clusters.flatMap((c) => c.families))].sort(),
    [clusters],
  );

  const totalJobs = filteredClusters.reduce((sum, c) => sum + c.count, 0);
  const maxJobCount = Math.max(1, ...filteredClusters.map((c) => c.count));

  const totalWorkers = (workers ?? []).reduce((s, w) => s + w.applicant_count, 0);
  const totalSignals = (flows ?? []).reduce((s, f) => s + f.count, 0);

  useEffect(() => {
    setTooltip(null);
    if (view === "workers" && workers === null) {
      setViewLoading(true);
      setViewError(null);
      fetchApplicantMap(accessToken)
        .then(setWorkers)
        .catch((err) => setViewError(err instanceof Error ? err.message : "Request failed"))
        .finally(() => setViewLoading(false));
    }
    if (view === "applications" && flows === null) {
      setViewLoading(true);
      setViewError(null);
      fetchApplicationFlows(accessToken)
        .then(setFlows)
        .catch((err) => setViewError(err instanceof Error ? err.message : "Request failed"))
        .finally(() => setViewLoading(false));
    }
    if (view === "supply" && supply === null && !supplyLoading && !supplyError) {
      loadSupply();
    }
  }, [view, workers, flows, accessToken, supply, supplyLoading, supplyError, loadSupply]);

  const loadClusterJobs = useCallback(
    async (city: string, state: string) => {
      setLoadingJobs(true);
      setJobsError(null);
      try {
        const jobs = await fetchClusterJobs(city, state, accessToken);
        setClusterJobs(jobs);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("[admin/map] cluster jobs fetch failed", err);
        setClusterJobs([]);
        setJobsError(err instanceof Error ? err.message : "Request failed");
      } finally {
        setLoadingJobs(false);
      }
    },
    [accessToken],
  );

  useEffect(() => {
    if (!selectedCluster) {
      setClusterJobs([]);
      setJobsError(null);
      return;
    }
    void loadClusterJobs(selectedCluster.city, selectedCluster.state);
  }, [selectedCluster, loadClusterJobs]);

  const showTooltip = useCallback((lines: string[], event: ReactMouseEvent) => {
    const rect = mapCardRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTooltip({ x: event.clientX - rect.left, y: event.clientY - rect.top, lines });
  }, []);

  const handleFlowHover = useCallback(
    (flow: ApplicationFlow | null, event?: ReactMouseEvent) => {
      if (!flow || !event) {
        setTooltip(null);
        return;
      }
      const workerNoun = flow.count === 1 ? "worker" : "workers";
      showTooltip(
        [
          `${flow.count} ${workerNoun} in ${flow.from.city}, ${flow.from.state}`,
          flow.from.city === flow.to.city && flow.from.state === flow.to.state
            ? "applied to jobs in their own city"
            : `applied to jobs in ${flow.to.city}, ${flow.to.state}`,
        ],
        event,
      );
    },
    [showTooltip],
  );

  const insight = useMemo(() => (flows ? flowInsight(flows) : null), [flows]);

  // One computed takeaway per view — always derived from the data on screen.
  const jobsInsight = useMemo(() => {
    if (filteredClusters.length === 0 || totalJobs === 0) return null;
    const top = [...filteredClusters].sort((a, b) => b.count - a.count)[0];
    return `${top.city}, ${top.state} is the largest cluster: ${top.count.toLocaleString()} of ${totalJobs.toLocaleString()} jobs (${pctLabel(top.count, totalJobs)}).`;
  }, [filteredClusters, totalJobs]);

  const workersInsight = useMemo(() => {
    if (!workers || workers.length === 0 || totalWorkers === 0) return null;
    const top = [...workers].sort((a, b) => b.applicant_count - a.applicant_count)[0];
    return `${top.city}, ${top.state} is the largest worker hub: ${top.applicant_count.toLocaleString()} of ${totalWorkers.toLocaleString()} (${pctLabel(top.applicant_count, totalWorkers)}).`;
  }, [workers, totalWorkers]);

  const supplyInsight = useMemo(() => {
    if (!supply || supply.geo.clusters.length === 0) return null;
    const top = supply.geo.clusters[0]; // server sorts by combined volume
    return `${top.label} is the largest market: ${top.workers.toLocaleString()} worker${top.workers === 1 ? "" : "s"}, ${top.jobs.toLocaleString()} open job${top.jobs === 1 ? "" : "s"}.`;
  }, [supply]);

  const viewInsight =
    view === "jobs"
      ? jobsInsight
      : view === "workers"
        ? workersInsight
        : view === "supply"
          ? supplyInsight
          : insight;

  // Direct-label the top clusters so the map answers "where?" without hovering.
  const labeledJobKeys = useMemo(() => {
    return new Set(
      [...filteredClusters]
        .sort((a, b) => b.count - a.count)
        .slice(0, 3)
        .map((c) => `${c.city}-${c.state}`),
    );
  }, [filteredClusters]);

  const labeledWorkerKeys = useMemo(() => {
    return new Set(
      [...(workers ?? [])]
        .sort((a, b) => b.applicant_count - a.applicant_count)
        .slice(0, 3)
        .map((w) => `${w.city}-${w.state}`),
    );
  }, [workers]);

  if (error) {
    return (
      <main className="p-8">
        <div className="max-w-5xl mx-auto bg-error-red/[0.06] border border-error-red/30 rounded-md p-6 text-cohere-ink">
          {error}
        </div>
      </main>
    );
  }

  const visibleJobs = familyFilter
    ? clusterJobs.filter((j) => (j.family_code ?? "").toLowerCase() === familyFilter.toLowerCase())
    : clusterJobs;

  const lead =
    view === "jobs"
      // Qualified count: the map only shows jobs WITH a mapped city/state, so
      // this number can be lower than "open jobs" on the dashboard — say so.
      ? `${totalJobs} jobs with mapped locations, across ${filteredClusters.length} ${filteredClusters.length === 1 ? "city" : "cities"}`
      : view === "workers"
        ? workers
          ? `${totalWorkers} worker${totalWorkers === 1 ? "" : "s"} across ${workers.length} ${workers.length === 1 ? "city" : "cities"}`
          : "Where workers live"
        : view === "supply"
          ? supply
            ? `${supply.families.total_workers.toLocaleString()} workers vs ${supply.families.total_jobs.toLocaleString()} open jobs across ${supply.geo.clusters.length} metro clusters`
            : "Where supply and demand sit"
          : flows
            ? `${totalSignals} application signal${totalSignals === 1 ? "" : "s"} across ${flows.length} route${flows.length === 1 ? "" : "s"}`
            : "Where applications travel";

  return (
    <main className="py-8 min-h-screen">
      <div className="page-shell space-y-5">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Map" }]} />

        <PageHeader
          eyebrow="Geography"
          title="Map"
          lead={lead}
          actions={
            view === "jobs" ? (
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-slate-muted" aria-hidden />
                <select
                  value={familyFilter}
                  onChange={(e) => setFamilyFilter(e.target.value)}
                  className="input-cohere text-caption px-3 py-2 w-auto"
                  aria-label="Filter by trade family"
                >
                  <option value="">All trades</option>
                  {allFamilies.map((f) => (
                    <option key={f} value={f}>
                      {familyLabel(f)}
                    </option>
                  ))}
                </select>
                {familyFilter && (
                  <button
                    onClick={() => setFamilyFilter("")}
                    className="p-1 text-slate-muted hover:text-slate transition-colors"
                    aria-label="Clear filter"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
            ) : undefined
          }
        />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <ViewToggle<MapView>
            value={view}
            onChange={setView}
            ariaLabel="Map view"
            options={[
              { value: "jobs", label: "Jobs" },
              { value: "workers", label: "Workers" },
              { value: "applications", label: "Applications" },
              { value: "supply", label: "Supply vs demand" },
            ]}
          />
          {viewInsight && <p className="text-caption text-slate">{viewInsight}</p>}
        </div>

        {/* Fourth view — the self-contained two-sided supply/demand composite
            (own map frame + cross-filtered companion bars). Rendered in its
            own white sheet; the three original views below stay untouched. */}
        {view === "supply" ? (
          <div className="rounded-md border border-hairline bg-white p-5">
            {supplyError ? (
              <div>
                <p className="text-body text-cohere-ink">
                  Could not load supply and demand. {supplyError}
                </p>
                <button
                  onClick={loadSupply}
                  className="btn-ghost btn-sm mt-2 inline-flex items-center gap-1"
                >
                  <RefreshCw className="h-3 w-3" /> Retry
                </button>
              </div>
            ) : supply ? (
              <SupplyDemandMap
                clusters={supply.geo.clusters}
                families={supply.families.families}
              />
            ) : (
              <SupplyDemandSkeleton />
            )}
          </div>
        ) : (
        <>
        {/* Two-column: map on the left, detail panel on the right (desktop);
            panel stacks below on mobile.

            The row is a FIXED-HEIGHT grid on desktop so the map's box never
            depends on the panel's content length (1 job vs. 16 jobs) or on the
            selected view. The panel scrolls inside that height instead. */}
        <div className="grid grid-cols-1 lg:h-[560px] lg:grid-cols-[minmax(0,1fr)_360px] gap-5">
          {/* Map card — editorial cream surface, no tile provider, no attribution bar */}
          <div
            ref={mapCardRef}
            data-tour-id="map-canvas"
            className="relative aspect-[16/10] overflow-hidden rounded-md border border-hairline bg-white lg:aspect-auto lg:h-full"
          >
            <div className="pointer-events-none absolute bottom-3 right-4 z-[1] text-micro text-slate-muted/60">
              Data, SKILLED Nation
            </div>

            {viewLoading && view !== "jobs" && (
              <div className="absolute inset-0 z-[2] flex items-center justify-center bg-white/60">
                <div className="flex items-center gap-2 text-caption text-slate-muted">
                  <div className="w-4 h-4 border-2 border-hairline border-t-cohere-ink rounded-full animate-spin" />
                  Loading…
                </div>
              </div>
            )}
            {viewError && view !== "jobs" && (
              <div className="absolute inset-x-0 top-0 z-[2] border-b border-error-red/30 bg-error-red/[0.06] px-4 py-2 text-caption text-cohere-ink">
                Could not load this view. {viewError}
              </div>
            )}

            <UsMapFrame>
              {({ k, projection }) => (
                <>
                  {view === "jobs" &&
                    filteredClusters.map((cluster) => {
                      if (!Number.isFinite(cluster.lat) || !Number.isFinite(cluster.lon)) return null;
                      const primary = cluster.families[0] ?? "unknown";
                      const color = FAMILY_COLORS[primary] ?? DEFAULT_MARKER_COLOR;
                      const radius = Math.max(4, Math.min(20, (cluster.count / maxJobCount) * 18 + 4));
                      const isSelected =
                        selectedCluster?.city === cluster.city &&
                        selectedCluster?.state === cluster.state;

                      return (
                        <Marker
                          key={`${cluster.city}-${cluster.state}`}
                          coordinates={[cluster.lon, cluster.lat]}
                          onClick={() => setSelectedCluster(cluster)}
                        >
                          <circle
                            r={radius / k}
                            fill={color}
                            fillOpacity={isSelected ? 0.95 : 0.75}
                            stroke={isSelected ? "#100904" : "#ffedd7"}
                            strokeWidth={(isSelected ? 1.5 : 1) / k}
                            style={{ cursor: "pointer", transition: "fill-opacity 150ms ease" }}
                          >
                            {/* Single template string — React rejects array
                                children on <title>. Text affordance for the
                                color-coded dot: place + count + lead trade. */}
                            <title>
                              {`${cluster.city}, ${cluster.state}, ${cluster.count} job${cluster.count !== 1 ? "s" : ""} · ${familyLabel(primary)}`}
                            </title>
                          </circle>
                          {/* Direct label on the biggest clusters — the map
                              should answer "where?" without a hover. */}
                          {labeledJobKeys.has(`${cluster.city}-${cluster.state}`) && (
                            <text
                              x={(radius + 5) / k}
                              y={4 / k}
                              fontSize={11 / k}
                              fontWeight={500}
                              fill="#33322f"
                              stroke="#ffffff"
                              strokeWidth={3 / k}
                              paintOrder="stroke"
                              style={{ pointerEvents: "none" }}
                            >
                              {`${cluster.city} · ${cluster.count}`}
                            </text>
                          )}
                        </Marker>
                      );
                    })}

                  {view === "workers" &&
                    (workers ?? []).map((w) => {
                      // Absolute sqrt sizing (not max-normalized) so a lone
                      // worker stays a small dot even in sparse datasets.
                      const radius = Math.min(16, 3 + 3 * Math.sqrt(w.applicant_count));
                      const noun = w.applicant_count === 1 ? "worker" : "workers";
                      return (
                        <Marker key={`${w.city}-${w.state}`} coordinates={[w.lng, w.lat]}>
                          <circle
                            r={radius / k}
                            fill={ACCENT}
                            fillOpacity={0.8}
                            stroke="#ffedd7"
                            strokeWidth={1 / k}
                            onMouseEnter={(e) =>
                              showTooltip([`${w.applicant_count} ${noun} · ${w.city}, ${w.state}`], e)
                            }
                            onMouseMove={(e) =>
                              showTooltip([`${w.applicant_count} ${noun} · ${w.city}, ${w.state}`], e)
                            }
                            onMouseLeave={() => setTooltip(null)}
                          />
                          {labeledWorkerKeys.has(`${w.city}-${w.state}`) && (
                            <text
                              x={(radius + 5) / k}
                              y={4 / k}
                              fontSize={11 / k}
                              fontWeight={500}
                              fill="#33322f"
                              stroke="#ffffff"
                              strokeWidth={3 / k}
                              paintOrder="stroke"
                              style={{ pointerEvents: "none" }}
                            >
                              {`${w.city} · ${w.applicant_count}`}
                            </text>
                          )}
                        </Marker>
                      );
                    })}

                  {view === "applications" && flows && flows.length > 0 && (
                    <FlowArcLayer flows={flows} projection={projection} k={k} onHover={handleFlowHover} />
                  )}
                </>
              )}
            </UsMapFrame>

            {view === "applications" && flows !== null && flows.length === 0 && !viewLoading && (
              <div className="absolute inset-0 z-[1] flex items-center justify-center">
                <p className="rounded-md border border-hairline bg-white px-4 py-2 text-caption text-slate-muted">
                  No application activity yet.
                </p>
              </div>
            )}

            {tooltip && (
              <div
                className="pointer-events-none absolute z-[3] max-w-[260px] rounded-md border border-hairline bg-white px-3 py-2 text-caption text-cohere-ink shadow-sm"
                style={{
                  left: Math.min(Math.max(tooltip.x, 8), (mapCardRef.current?.clientWidth ?? 400) - 140),
                  top: tooltip.y,
                  transform: "translate(-50%, calc(-100% - 12px))",
                }}
              >
                {tooltip.lines.map((line) => (
                  <div key={line}>{line}</div>
                ))}
              </div>
            )}
          </div>

          {/* Right-side detail panel (desktop) / slide-under (mobile) */}
          <aside className="flex min-h-0 flex-col lg:h-full" data-tour-id="map-panel">
            {view === "jobs" && selectedCluster ? (
              <div className="flex min-h-0 flex-col rounded-md border border-hairline bg-white p-5 lg:h-full">
                <div className="flex shrink-0 items-center justify-between mb-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <MapPin className="w-4 h-4 text-slate-muted shrink-0" aria-hidden />
                    <h3 className="text-[1.0625rem] font-medium text-cohere-ink truncate">
                      {selectedCluster.city}, {selectedCluster.state}
                    </h3>
                  </div>
                  <button
                    onClick={() => setSelectedCluster(null)}
                    className="text-slate-muted hover:text-slate transition-colors shrink-0"
                    aria-label="Close details"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <div className="flex shrink-0 items-baseline gap-2">
                  <span className="font-display text-card text-cohere-ink tabular-nums">
                    {selectedCluster.count}
                  </span>
                  <span className="text-caption text-slate">
                    active job{selectedCluster.count !== 1 ? "s" : ""}
                  </span>
                </div>

                <div className="mt-3 flex shrink-0 flex-wrap gap-1.5">
                  {selectedCluster.families.map((f) => (
                    <span
                      key={f}
                      className="text-micro px-2 py-0.5 rounded-xs border font-medium"
                      style={{
                        backgroundColor: `${FAMILY_COLORS[f] ?? DEFAULT_MARKER_COLOR}18`,
                        borderColor: `${FAMILY_COLORS[f] ?? DEFAULT_MARKER_COLOR}40`,
                        color: FAMILY_COLORS[f] ?? DEFAULT_MARKER_COLOR,
                      }}
                    >
                      {familyLabel(f)}
                    </span>
                  ))}
                </div>

                <div className="mt-4 flex min-h-0 flex-1 flex-col border-t border-hairline pt-3">
                  <MonoLabel className="mb-2 block shrink-0">
                    Jobs at this location
                    {familyFilter && (
                      <span className="ml-1 text-slate-muted">, filtered to {familyFilter}</span>
                    )}
                  </MonoLabel>

                  {loadingJobs ? (
                    <div className="flex items-center gap-2 py-4 justify-center text-slate-muted text-caption">
                      <div className="w-4 h-4 border-2 border-hairline border-t-cohere-ink rounded-full animate-spin" />
                      Loading jobs…
                    </div>
                  ) : jobsError ? (
                    <div className="rounded-md border border-error-red/30 bg-error-red/[0.06] p-3">
                      <div className="flex items-start gap-2 text-caption text-cohere-ink">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-error-red" aria-hidden />
                        <div className="flex-1">
                          <p className="font-medium">Could not load jobs for this location.</p>
                          <p className="text-slate-muted">{jobsError}</p>
                        </div>
                        <button
                          onClick={() =>
                            void loadClusterJobs(selectedCluster.city, selectedCluster.state)
                          }
                          className="btn-ghost btn-sm inline-flex items-center gap-1"
                        >
                          <RefreshCw className="h-3 w-3" /> Retry
                        </button>
                      </div>
                    </div>
                  ) : visibleJobs.length === 0 ? (
                    <p className="text-caption text-slate-muted py-2">
                      {familyFilter
                        ? `No ${familyFilter} jobs at this location.`
                        : "No jobs found."}
                    </p>
                  ) : (
                    <div className="-mx-1 min-h-0 flex-1 divide-y divide-hairline overflow-y-auto px-1 max-h-[360px] lg:max-h-none">
                      {visibleJobs.map((job) => (
                        <div key={job.id} className="flex items-center justify-between py-2">
                          <div className="flex-1 min-w-0">
                            <div className="text-caption font-medium text-cohere-ink truncate">
                              {job.title}
                            </div>
                            <div className="text-micro text-slate-muted truncate">
                              {job.employer}
                            </div>
                          </div>
                          <div className="flex items-center gap-2 ml-3 shrink-0">
                            {job.experience_level && (
                              <span className="text-micro px-2 py-0.5 rounded-xs bg-stone text-slate border border-hairline">
                                {job.experience_level}
                              </span>
                            )}
                            {job.source_url && (
                              <a
                                href={job.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-micro text-cohere-blue hover:underline whitespace-nowrap"
                              >
                                View <ExternalLink className="w-3 h-3 inline" aria-hidden />
                              </a>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="overflow-y-auto rounded-md border border-dashed border-hairline bg-white/60 p-5 text-caption text-slate-muted lg:h-full">
                <MonoLabel className="mb-2 block">How to read this</MonoLabel>
                {view === "jobs" && (
                  <p>
                    Circles are city clusters. Size scales with active job count, color reflects the
                    primary trade family. Click a marker for the job list. Scroll or pinch to zoom,
                    drag to pan, double-click to zoom in.
                  </p>
                )}
                {view === "workers" && (
                  <p>
                    Each dot is a city where workers live, sized by how many live there. Counts only,
                    no individual worker locations shown. Hover a dot for the count.
                  </p>
                )}
                {view === "applications" && (
                  <p>
                    Lines run from where workers live to the cities they applied in. An open ring
                    marks home, a filled dot marks the job city, and thicker lines carry more
                    applications. A ring by itself means workers applied in their own city. Hover any
                    line for detail.
                  </p>
                )}
              </div>
            )}
          </aside>
        </div>

        {/* Legend — adapts per view. Jobs: trade family chips double as filters.
            The wrapper reserves a fixed minimum height so switching views (or
            selecting a location) never shifts what sits below it. */}
        <div className="flex min-h-[30px] items-start">
        {view === "jobs" && (
          <div className="flex flex-wrap gap-2">
            {Object.entries(FAMILY_COLORS).map(([family, color]) => {
              const active = familyFilter === family;
              return (
                <button
                  key={family}
                  onClick={() => setFamilyFilter(active ? "" : family)}
                  className={`flex items-center gap-1.5 text-micro px-3 py-1.5 rounded-xs border transition-colors ${
                    active
                      ? "border-ink bg-ink text-white font-medium"
                      : "border-cohere-ink/25 text-ink hover:border-cohere-ink"
                  }`}
                  aria-pressed={active}
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: color }}
                  />
                  {familyLabel(family)}
                </button>
              );
            })}
          </div>
        )}
        {view === "workers" && (
          <p className="text-micro text-slate-muted">
            <span
              className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full align-[-1px]"
              style={{ backgroundColor: ACCENT }}
            />
            Worker cities, sized by count. Aggregated, never individual addresses.
          </p>
        )}
        {view === "applications" && (
          <p className="text-micro text-slate-muted">
            <span
              className="mr-1.5 inline-block h-2.5 w-2.5 rounded-full border align-[-1px]"
              style={{ borderColor: ACCENT }}
            />
            home city
            <span
              className="mx-1.5 ml-4 inline-block h-2.5 w-2.5 rounded-full align-[-1px]"
              style={{ backgroundColor: ACCENT }}
            />
            job city · line width scales with application volume
          </p>
        )}
        </div>
        </>
        )}
      </div>
    </main>
  );
}
