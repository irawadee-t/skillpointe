"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ComposableMap, Geographies, Geography, Marker } from "react-simple-maps";
import { ExternalLink, Filter, MapPin, RefreshCw, X, AlertTriangle } from "lucide-react";
import type { CityJobCluster, ClusterJob } from "@/lib/api/admin";
import { fetchClusterJobs } from "@/lib/api/admin";
import { Breadcrumb, MonoLabel, PageHeader } from "@/components/ui";

interface Props {
  clusters: CityJobCluster[];
  error: string | null;
  accessToken: string;
}

/**
 * Warm editorial palette — pulled straight from the studio-* tokens so the map
 * reads as part of the site, not a rainbow overlay.
 * Order matches the legend below (most common trades first).
 */
const FAMILY_COLORS: Record<string, string> = {
  electrical:    "#9E1B32", // studio-maroon
  welding:       "#dc5000", // studio-sienna
  hvac:          "#4a4b2f", // studio-forest (olive)
  manufacturing: "#382416", // studio-dark-cork
  automotive:    "#6c5f51", // studio-grey-brown
  construction:  "#b8621f", // burnt copper
  logistics:     "#2d3320", // deep forest
  aviation:      "#5c4033", // cocoa
};

const DEFAULT_MARKER_COLOR = "#5a4f42";

// Local topology bundled in /public — no external tile server, no attribution.
const TOPO_URL = "/us-states-10m.json";

function familyLabel(family: string) {
  return family.charAt(0).toUpperCase() + family.slice(1).replace(/_/g, " ");
}

export function JobMapClient({ clusters, error, accessToken }: Props) {
  const [familyFilter, setFamilyFilter] = useState<string>("");
  const [selectedCluster, setSelectedCluster] = useState<CityJobCluster | null>(null);
  const [clusterJobs, setClusterJobs] = useState<ClusterJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [jobsError, setJobsError] = useState<string | null>(null);

  const filteredClusters = useMemo(
    () => (familyFilter ? clusters.filter((c) => c.families.includes(familyFilter)) : clusters),
    [clusters, familyFilter],
  );

  const allFamilies = useMemo(
    () => [...new Set(clusters.flatMap((c) => c.families))].sort(),
    [clusters],
  );

  const totalJobs = filteredClusters.reduce((sum, c) => sum + c.count, 0);
  const maxCount = Math.max(1, ...filteredClusters.map((c) => c.count));

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

  if (error) {
    return (
      <main className="p-8">
        <div className="max-w-5xl mx-auto bg-cohere-coral/10 border border-cohere-coral-soft rounded-md p-6 text-cohere-ink">
          {error}
        </div>
      </main>
    );
  }

  const visibleJobs = familyFilter
    ? clusterJobs.filter((j) => (j.family_code ?? "").toLowerCase() === familyFilter.toLowerCase())
    : clusterJobs;

  return (
    <main className="py-8 min-h-screen">
      <div className="page-shell space-y-5">
        <Breadcrumb items={[{ label: "Admin", href: "/admin" }, { label: "Job map" }]} />

        <PageHeader
          eyebrow="Geography"
          title="Job map"
          lead={`${totalJobs} jobs across ${filteredClusters.length} locations`}
          actions={
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
          }
        />

        {/* Two-column: map on the left, detail panel on the right (desktop);
            panel stacks below on mobile. */}
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-5">
          {/* Map card — editorial cream surface, no tile provider, no attribution bar */}
          <div className="relative bg-white border border-hairline rounded-md overflow-hidden">
            <div className="pointer-events-none absolute bottom-3 right-4 z-[1] font-display text-[10px] uppercase tracking-[0.18em] text-slate-muted/60">
              Data, SKILLED Nation
            </div>

            <div className="w-full aspect-[16/10] lg:aspect-[16/9]">
              <ComposableMap
                projection="geoAlbersUsa"
                projectionConfig={{ scale: 1100 }}
                width={980}
                height={560}
                style={{ width: "100%", height: "100%" }}
              >
                <Geographies geography={TOPO_URL}>
                  {({ geographies }) =>
                    geographies.map((geo) => (
                      <Geography
                        key={geo.rsmKey}
                        geography={geo}
                        style={{
                          default: {
                            fill: "#f5f1e8",     // parchment
                            stroke: "#d9d5cc",   // hairline
                            strokeWidth: 0.6,
                            outline: "none",
                          },
                          hover: {
                            fill: "#eeece7",     // stone
                            stroke: "#40372e",   // studio-cork
                            strokeWidth: 0.75,
                            outline: "none",
                          },
                          pressed: {
                            fill: "#eeece7",
                            stroke: "#40372e",
                            strokeWidth: 0.75,
                            outline: "none",
                          },
                        }}
                      />
                    ))
                  }
                </Geographies>

                {filteredClusters.map((cluster) => {
                  if (!Number.isFinite(cluster.lat) || !Number.isFinite(cluster.lon)) return null;
                  const primary = cluster.families[0] ?? "unknown";
                  const color = FAMILY_COLORS[primary] ?? DEFAULT_MARKER_COLOR;
                  const radius = Math.max(4, Math.min(20, (cluster.count / maxCount) * 18 + 4));
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
                        r={radius}
                        fill={color}
                        fillOpacity={isSelected ? 0.95 : 0.75}
                        stroke={isSelected ? "#100904" : "#ffedd7"}
                        strokeWidth={isSelected ? 1.5 : 1}
                        style={{ cursor: "pointer", transition: "all 150ms ease" }}
                      >
                        <title>
                          {cluster.city}, {cluster.state}, {cluster.count} job
                          {cluster.count !== 1 ? "s" : ""}
                        </title>
                      </circle>
                    </Marker>
                  );
                })}
              </ComposableMap>
            </div>
          </div>

          {/* Right-side detail panel (desktop) / slide-under (mobile) */}
          <aside className="lg:sticky lg:top-4 h-fit">
            {selectedCluster ? (
              <div className="border border-hairline rounded-md bg-white p-5">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <MapPin className="w-4 h-4 text-slate-muted shrink-0" aria-hidden />
                    <h3 className="text-feature font-display text-cohere-ink truncate">
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
                <div className="flex items-baseline gap-2">
                  <span className="font-display text-card text-cohere-ink tabular-nums">
                    {selectedCluster.count}
                  </span>
                  <span className="text-caption text-slate">
                    active job{selectedCluster.count !== 1 ? "s" : ""}
                  </span>
                </div>

                <div className="mt-3 flex flex-wrap gap-1.5">
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

                <div className="mt-4 border-t border-hairline pt-3">
                  <MonoLabel className="mb-2 block">
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
                    <div className="rounded-md border border-cohere-coral/30 bg-cohere-coral/10 p-3">
                      <div className="flex items-start gap-2 text-caption text-cohere-ink">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-cohere-coral" aria-hidden />
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
                    <div className="max-h-[360px] overflow-y-auto -mx-1 px-1 divide-y divide-hairline">
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
              <div className="border border-hairline border-dashed rounded-md bg-white/60 p-5 text-caption text-slate-muted">
                <MonoLabel className="mb-2 block">How to read this</MonoLabel>
                <p>
                  Circles are city clusters — size scales with active job count, color reflects the
                  primary trade family. Click a marker for the job list.
                </p>
              </div>
            )}
          </aside>
        </div>

        {/* Legend — trade family chips double as filters (matches app-wide chip pattern) */}
        <div className="flex flex-wrap gap-2">
          {Object.entries(FAMILY_COLORS).map(([family, color]) => {
            const active = familyFilter === family;
            return (
              <button
                key={family}
                onClick={() => setFamilyFilter(active ? "" : family)}
                className={`flex items-center gap-1.5 text-micro px-3 py-1.5 rounded-xs border transition-colors ${
                  active
                    ? "border-studio-dark-cork bg-studio-dark-cork text-studio-cream font-medium"
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
      </div>
    </main>
  );
}
