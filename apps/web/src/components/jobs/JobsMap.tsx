"use client";

/**
 * JobsMap — the Airbnb-style map pane for /applicant/jobs.
 *
 * Renders every job matching the CURRENT browse filters as a pin on the shared
 * UsMapFrame (react-simple-maps + d3-geo — no tile service, no SDK). Nearby
 * pins grid-cluster into count bubbles that split on zoom (or click). The
 * list and the map stay in sync through hover/select ids owned by
 * JobBrowseClient. When a center + radius are active, a translucent radius
 * circle and a "you are here" dot are drawn and the view auto-fits.
 *
 * Smoothness contract (shared with UsMapFrame): pins project once per data
 * change, clusters re-bucket only when zoom crosses an octave (1x/2x/4x/8x),
 * so a wheel gesture animates one cheap marker layer and the bubbles never
 * churn mid-gesture. Programmatic zooms glide via the frame's tween.
 *
 * Design contract: white/hairline/ink, single maroon accent, no pin
 * animations (static under prefers-reduced-motion and everywhere else).
 */

import { useEffect, useMemo, useRef } from "react";
import type { GeoProjection } from "d3";
import { geoCircle, geoPath } from "d3";
import { MAX_ZOOM, UsMapFrame, type UsMapFrameApi } from "@/components/viz";
import {
  MILES_PER_DEGREE,
  clusterPoints,
  formatPinPay,
  truncateLabel,
} from "@/lib/mapCluster";
import type { MapView } from "@/lib/mapViewport";

export interface JobPin {
  job_id: string;
  title: string;
  employer_name: string;
  city: string | null;
  state: string | null;
  lat: number;
  lng: number;
  pay_min: number | null;
  pay_max: number | null;
  pay_type: string | null;
  pay_raw: string | null;
  source_url: string | null;
  internal_apply: boolean;
  distance_miles: number | null;
}

const ACCENT = "#9d2235"; // studio maroon — the single brand accent
const INK = "#17171c";
const HAIRLINE = "#e7e5e2";
const SLATE = "#5c5a55";
const PIN_SHADOW = "drop-shadow(0 1px 2px rgba(23, 23, 28, 0.28))";

interface Props {
  pins: JobPin[];
  /** Filter-level pin total (before the 500 cap). */
  totalPins: number;
  /** Jobs matching the filters that have no coordinates (list-only). */
  withoutCoords: number;
  /** Radius-scope decoration: the translucent circle + "you are here" dot.
   *  Framing is separate (see `framing`). */
  center: { lat: number; lng: number } | null;
  radiusMiles: number | null;
  /** Programmatic framing, applied whenever it changes: a view to zoom to,
   *  "national" to reset to the home frame (Anywhere), or null to leave the
   *  map wherever the user put it. */
  framing?: MapView | "national" | null;
  /** Fires when the USER pans/zooms (never for programmatic framing), with
   *  the settled center + zoom — powers search-as-you-move. */
  onUserViewChange?: (view: MapView) => void;
  /** Show the bottom-left "N without a mapped location" chip. The map-area
   *  scope tells that story in the list's count line instead. */
  showUnmappedNote?: boolean;
  /** Job hovered in the LIST — its pin enlarges (Airbnb list→map sync). */
  hoveredId: string | null;
  /** Pin hovered/selected on the MAP — shows the popover card. */
  activeId: string | null;
  onActivate: (id: string | null) => void;
  /** "View" on the popover — scrolls/highlights the list card when present. */
  onViewInList: (id: string) => void;
  /** Job ids present on the current list page (popover "View" affordance). */
  listIds: Set<string>;
}

export function JobsMap({
  pins,
  totalPins,
  withoutCoords,
  center,
  radiusMiles,
  framing = null,
  onUserViewChange,
  showUnmappedNote = true,
  hoveredId,
  activeId,
  onActivate,
  onViewInList,
  listIds,
}: Props) {
  const apiRef = useRef<UsMapFrameApi | null>(null);

  // Programmatic framing — applied whenever the target changes. A null
  // framing never moves the map (the user is driving it).
  const fitKey =
    framing === "national"
      ? "national"
      : framing
        ? `${framing.lng},${framing.lat},${framing.zoom}`
        : "";
  useEffect(() => {
    if (!fitKey) return;
    // The frame mounts client-side a beat later; retry until the API exists.
    let tries = 0;
    let timer: number | undefined;
    const attempt = () => {
      if (apiRef.current) {
        if (framing === "national") {
          apiRef.current.reset();
        } else if (framing) {
          apiRef.current.zoomTo([framing.lng, framing.lat], framing.zoom);
        }
      } else if (tries++ < 20) {
        timer = window.setTimeout(attempt, 100);
      }
    };
    attempt();
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);

  return (
    // Leaving the map clears the popover (it reappears on the next pin hover).
    <div
      className="relative h-full w-full"
      data-testid="jobs-map"
      onMouseLeave={() => onActivate(null)}
    >
      <UsMapFrame
        apiRef={apiRef}
        onUserViewChange={(pos) =>
          onUserViewChange?.({ lng: pos.coordinates[0], lat: pos.coordinates[1], zoom: pos.zoom })
        }
      >
        {({ k, projection }) => (
          <PinLayer
            pins={pins}
            k={k}
            projection={projection}
            center={center}
            radiusMiles={radiusMiles}
            hoveredId={hoveredId}
            activeId={activeId}
            onActivate={onActivate}
            onViewInList={onViewInList}
            listIds={listIds}
            apiRef={apiRef}
            onUserViewChange={onUserViewChange}
          />
        )}
      </UsMapFrame>

      {pins.length === 0 && (
        <div className="absolute inset-0 z-[1] flex items-center justify-center">
          <p className="pointer-events-none rounded-full border border-hairline bg-white/95 px-4 py-2 text-caption text-slate">
            {radiusMiles ? "No jobs in this area. Widen the radius." : "No jobs to map."}
          </p>
        </div>
      )}

      {((showUnmappedNote && withoutCoords > 0) || totalPins > pins.length) && (
        <div className="pointer-events-none absolute bottom-3 left-3 z-[1] max-w-[85%] space-y-1">
          {showUnmappedNote && withoutCoords > 0 && (
            <p className="inline-block rounded-full border border-hairline bg-white/95 px-2.5 py-1 text-micro text-slate-muted">
              {withoutCoords} job{withoutCoords !== 1 ? "s" : ""} without a mapped location, shown
              in the list only
            </p>
          )}
          {totalPins > pins.length && pins.length > 0 && (
            <p className="block">
              <span className="inline-block rounded-full border border-hairline bg-white/95 px-2.5 py-1 text-micro text-slate-muted">
                Showing the first {pins.length} of {totalPins} mapped jobs
              </span>
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** All marker drawing lives here so hooks can memoize the expensive parts:
 *  pins project once per data change; clusters re-bucket per zoom OCTAVE. */
function PinLayer({
  pins,
  k,
  projection,
  center,
  radiusMiles,
  hoveredId,
  activeId,
  onActivate,
  onViewInList,
  listIds,
  apiRef,
  onUserViewChange,
}: {
  pins: JobPin[];
  k: number;
  projection: GeoProjection;
  center: { lat: number; lng: number } | null;
  radiusMiles: number | null;
  hoveredId: string | null;
  activeId: string | null;
  onActivate: (id: string | null) => void;
  onViewInList: (id: string) => void;
  listIds: Set<string>;
  apiRef: React.MutableRefObject<UsMapFrameApi | null>;
  onUserViewChange?: (view: MapView) => void;
}) {
  const byId = useMemo(() => new Map(pins.map((p) => [p.job_id, p])), [pins]);

  // Projection is zoom-invariant (zoom is a group transform), so project each
  // pin exactly once per data change — never per wheel frame.
  const projected = useMemo(
    () =>
      pins
        .map((p) => {
          const xy = projection([p.lng, p.lat]);
          return xy ? { id: p.job_id, x: xy[0], y: xy[1] } : null;
        })
        .filter((p): p is { id: string; x: number; y: number } => p !== null),
    [pins, projection],
  );
  const pointById = useMemo(() => new Map(projected.map((p) => [p.id, p])), [projected]);

  // Clusters re-bucket on octave crossings (1x → 2x → 4x → 8x), not per wheel
  // tick — bubbles hold steady through a gesture, then split as you arrive.
  const kOctave = Math.pow(2, Math.round(Math.log2(Math.max(1, k))));
  const clusters = useMemo(
    () => clusterPoints(projected, 40 / kOctave),
    [projected, kOctave],
  );

  const centerXY = center ? projection([center.lng, center.lat]) : null;
  const radiusPathD = useMemo(
    () =>
      center && radiusMiles
        ? geoPath(projection)(
            geoCircle()
              .center([center.lng, center.lat])
              .radius(radiusMiles / MILES_PER_DEGREE)(),
          )
        : null,
    [center, radiusMiles, projection],
  );

  const activePin = activeId ? byId.get(activeId) : null;
  const activeXY = activePin ? projection([activePin.lng, activePin.lat]) : null;

  return (
    <>
      {/* Radius circle + user location — under the pins, non-interactive */}
      {radiusPathD && (
        <path
          d={radiusPathD}
          fill={ACCENT}
          fillOpacity={0.05}
          stroke={ACCENT}
          strokeOpacity={0.35}
          strokeWidth={1 / k}
          pointerEvents="none"
        />
      )}
      {centerXY && (
        <g pointerEvents="none">
          <circle cx={centerXY[0]} cy={centerXY[1]} r={8 / k} fill={INK} fillOpacity={0.15} />
          <circle
            cx={centerXY[0]}
            cy={centerXY[1]}
            r={4.5 / k}
            fill={INK}
            stroke="#ffffff"
            strokeWidth={1.5 / k}
          />
        </g>
      )}

      {clusters.map((cluster) => {
        if (cluster.ids.length === 1) {
          const pin = byId.get(cluster.ids[0]);
          if (!pin) return null;
          const isActive = pin.job_id === activeId;
          const isHoveredFromList = pin.job_id === hoveredId;
          const emphasized = isActive || isHoveredFromList;
          return (
            <circle
              key={cluster.key}
              cx={cluster.x}
              cy={cluster.y}
              r={(emphasized ? 12 : 9) / k}
              fill={emphasized ? INK : ACCENT}
              fillOpacity={0.94}
              stroke="#ffffff"
              strokeWidth={2.25 / k}
              style={{ cursor: "pointer", filter: PIN_SHADOW }}
              onMouseEnter={() => onActivate(pin.job_id)}
              onClick={(e) => {
                e.stopPropagation();
                onActivate(pin.job_id);
                if (listIds.has(pin.job_id)) onViewInList(pin.job_id);
              }}
            />
          );
        }

        // Count bubble — white pill with ink count; click zooms in.
        const count = cluster.ids.length;
        const r = Math.min(27, 15 + 2.2 * Math.sqrt(count)) / k;
        const holdsEmphasis =
          (hoveredId !== null && cluster.ids.includes(hoveredId)) ||
          (activeId !== null && cluster.ids.includes(activeId));
        // Co-located jobs (same geocoded city centroid) can never split by
        // zooming — clicking such a bubble (or any bubble at max zoom) opens
        // the first job's card instead of dead-ending.
        const memberPts = cluster.ids
          .map((id) => pointById.get(id))
          .filter(Boolean) as { x: number; y: number }[];
        const unsplittable =
          k >= MAX_ZOOM - 0.1 ||
          memberPts.every(
            (p) => Math.abs(p.x - cluster.x) < 0.01 && Math.abs(p.y - cluster.y) < 0.01,
          );
        return (
          <g
            key={cluster.key}
            style={{ cursor: "pointer", filter: PIN_SHADOW }}
            onClick={(e) => {
              e.stopPropagation();
              if (unsplittable) {
                onActivate(cluster.ids[0]);
                return;
              }
              onActivate(null);
              const coords = projection.invert?.([cluster.x, cluster.y]);
              if (coords) {
                const nextZoom = Math.min(MAX_ZOOM, k * 2.2);
                apiRef.current?.zoomTo(coords as [number, number], nextZoom);
                // A cluster-split zoom is a user move — search-as-you-move
                // should narrow the list to the area it reveals.
                onUserViewChange?.({
                  lng: (coords as [number, number])[0],
                  lat: (coords as [number, number])[1],
                  zoom: nextZoom,
                });
              }
            }}
          >
            <circle
              cx={cluster.x}
              cy={cluster.y}
              r={r}
              fill="#ffffff"
              stroke={holdsEmphasis ? INK : ACCENT}
              strokeWidth={(holdsEmphasis ? 2 : 1.5) / k}
            >
              <title>{`${count} jobs. Click to zoom in.`}</title>
            </circle>
            <text
              x={cluster.x}
              y={cluster.y}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={15 / k}
              fontWeight={700}
              fill={INK}
              pointerEvents="none"
            >
              {count}
            </text>
          </g>
        );
      })}

      {/* Popover card for the active pin — white hairline sheet, counter-
          scaled so it stays a constant screen size. */}
      {activePin && activeXY && (
        <g
          transform={`translate(${activeXY[0]}, ${activeXY[1]}) scale(${1 / k})`}
          style={{
            cursor: listIds.has(activePin.job_id) ? "pointer" : "default",
            filter: "drop-shadow(0 4px 12px rgba(23, 23, 28, 0.18))",
          }}
          onClick={(e) => {
            e.stopPropagation();
            if (listIds.has(activePin.job_id)) onViewInList(activePin.job_id);
          }}
        >
          <rect
            x={-138}
            y={-122}
            width={276}
            height={102}
            rx={12}
            fill="#ffffff"
            stroke={HAIRLINE}
            strokeWidth={1}
          />
          <text x={-122} y={-92} fontSize={16.5} fontWeight={600} fill={INK}>
            {truncateLabel(activePin.title, 30)}
          </text>
          <text x={-122} y={-71} fontSize={14} fill={SLATE}>
            {truncateLabel(activePin.employer_name, 34)}
          </text>
          <text x={-122} y={-51} fontSize={14} fill={SLATE}>
            {truncateLabel(
              [
                formatPinPay(activePin),
                activePin.distance_miles !== null
                  ? activePin.distance_miles < 1
                    ? "<1 mi"
                    : `~${Math.round(activePin.distance_miles)} mi`
                  : [activePin.city, activePin.state].filter(Boolean).join(", ") || null,
              ]
                .filter(Boolean)
                .join(" · "),
              34,
            )}
          </text>
          <text x={-122} y={-31} fontSize={13.5} fontWeight={600} fill={ACCENT}>
            {listIds.has(activePin.job_id) ? "View in list" : ""}
          </text>
        </g>
      )}
    </>
  );
}
