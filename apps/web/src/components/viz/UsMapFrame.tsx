"use client";

/**
 * UsMapFrame — shared zoomable USA map shell for the admin geo views.
 *
 * Wraps react-simple-maps (d3-zoom under the hood) with:
 *   - wheel / pinch zoom (1x–8x), drag pan, double-click zoom
 *   - a quiet "Reset view" affordance when the view is transformed
 *   - a render-prop that hands children the live zoom factor `k` and the
 *     projection, so marker/arc layers can counter-scale to constant
 *     screen size while sharing one zoom state across views.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { MutableRefObject, ReactNode } from "react";
import { ComposableMap, Geographies, Geography, ZoomableGroup } from "react-simple-maps";
import { geoAlbersUsa } from "d3";
import type { GeoProjection } from "d3";
import { MAP_HEIGHT, MAP_SCALE, MAP_WIDTH } from "@/lib/mapViewport";

// Re-exported for existing callers; the values live in lib/mapViewport so the
// pure viewport math (server + tests) shares the exact frame constants.
export { MAP_WIDTH, MAP_HEIGHT };

// Local topology bundled in /public — no external tile server, no attribution.
const TOPO_URL = "/us-states-10m.json";

export interface MapLayerContext {
  /** Current zoom factor. Divide radii/stroke widths by k for constant screen size. */
  k: number;
  /** Identical parameters to the projection react-simple-maps builds internally. */
  projection: GeoProjection;
}

interface Position {
  coordinates: [number, number];
  zoom: number;
}

/** Imperative handle for callers that need programmatic zoom (cluster
 *  expansion, "fit the radius circle") without owning the zoom state. */
export interface UsMapFrameApi {
  zoomTo: (coordinates: [number, number], zoom: number) => void;
  reset: () => void;
}

interface Props {
  children: (ctx: MapLayerContext) => ReactNode;
  /** Optional — populated with the zoom API once mounted. Additive; existing
   *  callers (admin map) pass nothing and behave exactly as before. */
  apiRef?: MutableRefObject<UsMapFrameApi | null>;
  /** Fires after a USER pan/zoom gesture settles, with the new geographic
   *  center and zoom. Programmatic moves (zoomTo/reset — react-simple-maps
   *  bypasses its d3 handlers for prop-driven transforms) never fire this,
   *  so callers can treat it as "the user moved the map". */
  onUserViewChange?: (view: { coordinates: [number, number]; zoom: number }) => void;
}

export function UsMapFrame({ children, apiRef, onUserViewChange }: Props) {
  // Mirror of the projection ComposableMap constructs from
  // projection="geoAlbersUsa" + projectionConfig — same scale, same translate.
  const projection = useMemo<GeoProjection>(
    () => geoAlbersUsa().scale(MAP_SCALE).translate([MAP_WIDTH / 2, MAP_HEIGHT / 2]),
    [],
  );

  const defaultCenter = useMemo<[number, number]>(() => {
    const c = projection.invert?.([MAP_WIDTH / 2, MAP_HEIGHT / 2]);
    return (c as [number, number] | null) ?? [-96.6, 38.7];
  }, [projection]);

  const [position, setPosition] = useState<Position>({ coordinates: defaultCenter, zoom: 1 });
  const [k, setK] = useState(1);
  const [transformed, setTransformed] = useState(false);

  // Client-only render. d3-geo projection math produces float results that
  // differ in the last decimals between the server and browser builds, so the
  // SSR'd marker transforms never byte-match the client's — React logged a
  // hydration-mismatch error on every /admin/map load. Skipping SSR for the
  // map (it's an interactive, admin-only viz — nothing to index or stream)
  // removes the mismatch and ~100kB of dead SVG from the HTML payload.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const handleMove = useCallback(({ zoom }: { x: number; y: number; zoom: number }) => {
    setK(zoom);
    setTransformed(true);
  }, []);

  const handleMoveEnd = useCallback(
    (pos: { coordinates: [number, number]; zoom: number }) => {
      setPosition(pos);
      setK(pos.zoom);
      const atHome =
        pos.zoom < 1.02 &&
        Math.abs(pos.coordinates[0] - defaultCenter[0]) < 0.1 &&
        Math.abs(pos.coordinates[1] - defaultCenter[1]) < 0.1;
      setTransformed(!atHome);
      if (
        Number.isFinite(pos.coordinates?.[0]) &&
        Number.isFinite(pos.coordinates?.[1]) &&
        Number.isFinite(pos.zoom)
      ) {
        onUserViewChange?.(pos);
      }
    },
    [defaultCenter, onUserViewChange],
  );

  const reset = useCallback(() => {
    setPosition({ coordinates: defaultCenter, zoom: 1 });
    setK(1);
    setTransformed(false);
  }, [defaultCenter]);

  const zoomTo = useCallback((coordinates: [number, number], zoom: number) => {
    const z = Math.max(1, Math.min(8, zoom));
    setPosition({ coordinates, zoom: z });
    setK(z);
    setTransformed(true);
  }, []);

  useEffect(() => {
    if (!apiRef) return;
    apiRef.current = { zoomTo, reset };
    return () => {
      apiRef.current = null;
    };
  }, [apiRef, zoomTo, reset]);

  if (!mounted) {
    // Same box, quiet placeholder — the topo JSON fetch already keeps the
    // real map from painting for a beat, so this adds no perceived delay.
    return <div className="relative h-full w-full" aria-hidden />;
  }

  return (
    // Fills whatever box the caller gives it. The caller owns the height so a
    // sibling panel can never drive the map's size.
    <div className="relative h-full w-full">
      {transformed && (
        <button
          onClick={() => {
            reset();
            // The button is a user gesture: report the home view so
            // search-as-you-move callers widen their scope with it.
            onUserViewChange?.({ coordinates: defaultCenter, zoom: 1 });
          }}
          className="absolute top-3 right-3 z-[2] rounded-xs border border-hairline bg-white/90 px-2.5 py-1 text-caption text-slate transition-colors hover:text-cohere-ink"
        >
          Reset view
        </button>
      )}

      <ComposableMap
        projection="geoAlbersUsa"
        projectionConfig={{ scale: MAP_SCALE }}
        width={MAP_WIDTH}
        height={MAP_HEIGHT}
        style={{ width: "100%", height: "100%" }}
      >
        <ZoomableGroup
          center={position.coordinates}
          zoom={position.zoom}
          minZoom={1}
          maxZoom={8}
          translateExtent={[
            [0, 0],
            [MAP_WIDTH, MAP_HEIGHT],
          ]}
          // Default filter blocks ctrlKey events, which is what trackpad
          // pinches arrive as — allow everything except non-primary buttons.
          filterZoomEvent={(evt) => {
            const e = evt as unknown as { button?: number };
            return !e.button;
          }}
          onMove={handleMove}
          onMoveEnd={handleMoveEnd}
        >
          <Geographies geography={TOPO_URL}>
            {({ geographies }) =>
              geographies.map((geo) => (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  tabIndex={-1}
                  // States are decorative context, never a selection target —
                  // only markers (and arcs) are interactive. pointerEvents:none
                  // also lets zoom/pan gestures pass straight through to the
                  // ZoomableGroup, so the frame keeps its wheel/drag behaviour.
                  style={{
                    default: {
                      fill: "#f5f5f4", // parchment
                      stroke: "#e7e5e2", // hairline
                      strokeWidth: 0.6 / k,
                      outline: "none",
                      pointerEvents: "none",
                      cursor: "inherit",
                    },
                    hover: {
                      fill: "#f5f5f4",
                      stroke: "#e7e5e2",
                      strokeWidth: 0.6 / k,
                      outline: "none",
                      pointerEvents: "none",
                      cursor: "inherit",
                    },
                    pressed: {
                      fill: "#f5f5f4",
                      stroke: "#e7e5e2",
                      strokeWidth: 0.6 / k,
                      outline: "none",
                      pointerEvents: "none",
                      cursor: "inherit",
                    },
                  }}
                />
              ))
            }
          </Geographies>

          {children({ k, projection })}
        </ZoomableGroup>
      </ComposableMap>
    </div>
  );
}
