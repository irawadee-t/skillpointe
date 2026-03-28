"use client";

import { useEffect, useRef, useState } from "react";
import { MapPin, Filter, X, ExternalLink } from "lucide-react";
import type { CityJobCluster, ClusterJob } from "@/lib/api/admin";
import { fetchClusterJobs } from "@/lib/api/admin";

/* eslint-disable @typescript-eslint/no-explicit-any */

interface Props {
  clusters: CityJobCluster[];
  error: string | null;
  accessToken: string;
}

const FAMILY_COLORS: Record<string, string> = {
  electrical: "#f59e0b",
  welding: "#ef4444",
  hvac: "#3b82f6",
  manufacturing: "#10b981",
  automotive: "#8b5cf6",
  construction: "#f97316",
  logistics: "#06b6d4",
  aviation: "#6366f1",
};

function getL(): any {
  return (window as any).L;
}

function renderMarkers(
  map: any,
  markersLayer: any,
  clusters: CityJobCluster[],
  onSelect: (c: CityJobCluster) => void,
) {
  const L = getL();
  markersLayer.clearLayers();
  const maxCount = Math.max(...clusters.map((c) => c.count), 1);

  clusters.forEach((cluster) => {
    // Skip any cluster with invalid coords
    if (!Number.isFinite(cluster.lat) || !Number.isFinite(cluster.lon)) return;

    const radius = Math.max(8, Math.min(40, (cluster.count / maxCount) * 40 + 6));
    const primaryFamily = cluster.families[0] || "unknown";
    const color = FAMILY_COLORS[primaryFamily] || "#6b7280";

    const circle = L.circleMarker([cluster.lat, cluster.lon], {
      radius,
      fillColor: color,
      color: "#fff",
      weight: 2,
      opacity: 1,
      fillOpacity: 0.78,
    });

    circle.bindTooltip(
      `<div style="font-family:sans-serif;font-size:13px;line-height:1.5">
         <strong>${cluster.city}, ${cluster.state}</strong><br/>
         ${cluster.count} job${cluster.count !== 1 ? "s" : ""}
         <span style="font-size:11px;color:#666;display:block">${cluster.families.join(", ")}</span>
       </div>`,
      { direction: "top", offset: [0, -radius] },
    );

    circle.on("click", () => onSelect(cluster));
    markersLayer.addLayer(circle);
  });
}

export function JobMapClient({ clusters, error, accessToken }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<any>(null);
  const markersLayer = useRef<any>(null);
  const [loaded, setLoaded] = useState(false);
  const [selectedCluster, setSelectedCluster] = useState<CityJobCluster | null>(null);
  const [familyFilter, setFamilyFilter] = useState<string>("");
  const [clusterJobs, setClusterJobs] = useState<ClusterJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);

  const filteredClusters = familyFilter
    ? clusters.filter((c) => c.families.includes(familyFilter))
    : clusters;

  const allFamilies = [...new Set(clusters.flatMap((c) => c.families))].sort();
  const totalJobs = filteredClusters.reduce((sum, c) => sum + c.count, 0);

  // Initialize Leaflet map once
  useEffect(() => {
    if (mapInstance.current || !mapRef.current) return;

    // Inject Leaflet CSS
    if (!document.querySelector('link[href*="leaflet"]')) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(link);
    }

    const initMap = () => {
      if (mapInstance.current || !mapRef.current) return;
      const L = getL();

      const map = L.map(mapRef.current, {
        center: [38.5, -96.5],
        zoom: 4,
        scrollWheelZoom: true,
        zoomControl: true,
        preferCanvas: true,
      });

      L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
        attribution: "&copy; CARTO",
        maxZoom: 19,
      }).addTo(map);

      const layer = L.layerGroup().addTo(map);
      markersLayer.current = layer;
      mapInstance.current = map;

      // Force correct sizing after CSS and layout settle.
      // Use the ref (not the closed-over 'map') so that React 18 strict-mode's
      // double-invoke doesn't call invalidateSize on a removed map instance.
      setTimeout(() => {
        const m = mapInstance.current;
        if (!m || !markersLayer.current) return;
        m.invalidateSize();
        setLoaded(true);
      }, 300);
    };

    if ((window as any).L) {
      initMap();
    } else {
      const script = document.createElement("script");
      script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      script.onload = initMap;
      document.body.appendChild(script);
    }

    return () => {
      if (mapInstance.current) {
        mapInstance.current.remove();
        mapInstance.current = null;
        markersLayer.current = null;
      }
    };
  }, []);

  // Re-render markers whenever filter or load state changes
  useEffect(() => {
    if (!loaded || !mapInstance.current || !markersLayer.current) return;
    renderMarkers(mapInstance.current, markersLayer.current, filteredClusters, setSelectedCluster);
  }, [loaded, filteredClusters]);

  // Fetch actual jobs when a cluster is selected
  useEffect(() => {
    if (!selectedCluster) { setClusterJobs([]); return; }
    setLoadingJobs(true);
    fetchClusterJobs(selectedCluster.city, selectedCluster.state, accessToken)
      .then(setClusterJobs)
      .catch(() => setClusterJobs([]))
      .finally(() => setLoadingJobs(false));
  }, [selectedCluster, accessToken]);

  if (error) {
    return (
      <main className="p-8">
        <div className="max-w-5xl mx-auto bg-rose-50 border border-rose-200 rounded-lg p-6 text-rose-600">
          {error}
        </div>
      </main>
    );
  }

  return (
    <main className="p-6 md:p-8 min-h-screen">
      <div className="max-w-5xl mx-auto space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 flex items-center gap-2">
              <MapPin className="w-6 h-6" />
              Job Distribution Map
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              {totalJobs} jobs across {filteredClusters.length} locations
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-zinc-400" />
            <select
              value={familyFilter}
              onChange={(e) => { setFamilyFilter(e.target.value); setSelectedCluster(null); }}
              className="text-sm border border-zinc-200 rounded-lg px-3 py-1.5 bg-white text-zinc-900 focus:outline-none focus:ring-1 focus:ring-spf-navy/20 focus:border-spf-navy"
            >
              <option value="">All trades</option>
              {allFamilies.map((f) => (
                <option key={f} value={f}>
                  {f.charAt(0).toUpperCase() + f.slice(1).replace(/_/g, " ")}
                </option>
              ))}
            </select>
            {familyFilter && (
              <button onClick={() => setFamilyFilter("")} className="p-1 text-zinc-400 hover:text-zinc-600 transition-colors">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Map container — must have explicit height for Leaflet */}
        <div
          className="relative bg-zinc-50 border border-zinc-200 rounded-lg overflow-hidden"
          style={{ height: "520px" }}
        >
          <div ref={mapRef} style={{ width: "100%", height: "100%" }} />
          {!loaded && (
            <div className="absolute inset-0 flex items-center justify-center bg-zinc-50 z-10">
              <div className="flex items-center gap-2 text-zinc-500 text-sm">
                <div className="w-4 h-4 border-2 border-zinc-200 border-t-spf-navy rounded-full animate-spin" />
                Loading map…
              </div>
            </div>
          )}
        </div>

        {/* Legend */}
        <div className="flex flex-wrap gap-2">
          {Object.entries(FAMILY_COLORS).map(([family, color]) => (
            <button
              key={family}
              onClick={() => { setFamilyFilter(familyFilter === family ? "" : family); setSelectedCluster(null); }}
              className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all ${
                familyFilter === family
                  ? "border-zinc-200 bg-zinc-200 text-zinc-900 font-semibold"
                  : "border-zinc-200 text-zinc-500 hover:border-zinc-300 hover:text-zinc-700"
              }`}
            >
              <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
              {family.charAt(0).toUpperCase() + family.slice(1).replace(/_/g, " ")}
            </button>
          ))}
        </div>

        {/* Selected cluster panel */}
        {selectedCluster && (
          <div className="bg-zinc-50 border border-zinc-200 rounded-lg p-5">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <MapPin className="w-4 h-4 text-zinc-400" />
                <h3 className="font-semibold text-zinc-900">
                  {selectedCluster.city}, {selectedCluster.state}
                </h3>
              </div>
              <button onClick={() => setSelectedCluster(null)} className="text-zinc-400 hover:text-zinc-600 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold text-spf-navy">{selectedCluster.count}</span>
              <span className="text-sm text-zinc-500">active job{selectedCluster.count !== 1 ? "s" : ""}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {selectedCluster.families.map((f) => (
                <span
                  key={f}
                  className="text-xs px-2 py-0.5 rounded-full border font-medium"
                  style={{
                    backgroundColor: `${FAMILY_COLORS[f] || "#6b7280"}18`,
                    borderColor: `${FAMILY_COLORS[f] || "#6b7280"}40`,
                    color: FAMILY_COLORS[f] || "#6b7280",
                  }}
                >
                  {f}
                </span>
              ))}
            </div>

            {/* Job list drill-down */}
            <div className="mt-4 border-t border-zinc-200 pt-3">
              <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Jobs at this location</h4>
              {loadingJobs ? (
                <div className="flex items-center gap-2 py-4 justify-center text-zinc-400 text-sm">
                  <div className="w-4 h-4 border-2 border-zinc-200 border-t-spf-navy rounded-full animate-spin" />
                  Loading jobs…
                </div>
              ) : clusterJobs.length === 0 ? (
                <p className="text-sm text-zinc-400 py-2">No jobs found.</p>
              ) : (
                <div className="max-h-[300px] overflow-y-auto -mx-1 px-1">
                  {clusterJobs.map((job) => (
                    <div key={job.id} className="flex items-center justify-between py-2 border-b border-zinc-200 last:border-0">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-zinc-900 truncate">{job.title}</div>
                        <div className="text-xs text-zinc-400">{job.employer}</div>
                      </div>
                      <div className="flex items-center gap-2 ml-3">
                        {job.experience_level && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-zinc-100 text-zinc-500 border border-zinc-200">{job.experience_level}</span>
                        )}
                        {job.source_url && (
                          <a href={job.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-spf-navy hover:text-spf-navy-light transition-colors whitespace-nowrap">
                            View <ExternalLink className="w-3 h-3 inline" />
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
