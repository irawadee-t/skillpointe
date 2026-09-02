"use client";

/**
 * UsMapFrame — shared zoomable USA map shell for the geo views.
 *
 * Wraps react-simple-maps (d3-zoom under the hood) with:
 *   - wheel / pinch zoom (1x–10x), drag pan, double-click zoom
 *   - wheel + pinch captured over the map (never zooms/scrolls the page)
 *   - eased programmatic zoom (zoomTo/reset glide instead of jumping)
 *   - a quiet "Reset view" affordance when the view is transformed
 *   - a render-prop that hands children the live zoom factor `k` and the
 *     projection, so marker/arc layers can counter-scale to constant
 *     screen size while sharing one zoom state across views.
 *
 * Gesture smoothness contract: the state geographies are memoized against a
 * QUANTIZED zoom (they re-render a handful of times across the whole zoom
 * range, not per wheel tick), and `k` updates are rAF-coalesced — so a zoom
 * frame re-renders only the marker layer.
 */

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
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

export const MAX_ZOOM = 10;
const ZOOM_TWEEN_MS = 550;

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

/** The 50 state paths, isolated so a zoom frame never touches them. Stroke
 *  width tracks a coarse zoom bucket instead of the live k — visually
 *  identical, but the layer re-renders ~6 times across the zoom range
 *  instead of every wheel tick. */
const BaseGeographies = memo(function BaseGeographies({ kBucket }: { kBucket: number }) {
  const geoStyle = {
    fill: "#f5f5f4", // parchment
    stroke: "#e7e5e2", // hairline
    strokeWidth: 0.6 / kBucket,
    outline: "none",
    // States are decorative context, never a selection target — only markers
    // are interactive. pointerEvents:none also lets zoom/pan gestures pass
    // straight through to the ZoomableGroup.
    pointerEvents: "none" as const,
    cursor: "inherit",
  };
  return (
    <Geographies geography={TOPO_URL}>
      {({ geographies }) =>
        geographies.map((geo) => (
          <Geography
            key={geo.rsmKey}
            geography={geo}
            tabIndex={-1}
            style={{ default: geoStyle, hover: geoStyle, pressed: geoStyle }}
          />
        ))
      }
    </Geographies>
  );
});

const easeCubicOut = (t: number) => 1 - Math.pow(1 - t, 3);

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
  const containerRef = useRef<HTMLDivElement | null>(null);
  const animRef = useRef<number | null>(null);
  const positionRef = useRef(position);
  positionRef.current = position;

  // Client-only render. d3-geo projection math produces float results that
  // differ in the last decimals between the server and browser builds, so the
  // SSR'd marker transforms never byte-match the client's — React logged a
  // hydration-mismatch error on every /admin/map load. Skipping SSR for the
  // map (it's an interactive viz — nothing to index or stream) removes the
  // mismatch and ~100kB of dead SVG from the HTML payload.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // The browser's default for ctrl+wheel (trackpad pinch) is PAGE zoom, and
  // plain wheel scrolls the page — both fight the map. Capture wheel over the
  // map with a non-passive listener so gestures only ever move the map.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const swallow = (e: WheelEvent) => e.preventDefault();
    el.addEventListener("wheel", swallow, { passive: false });
    return () => el.removeEventListener("wheel", swallow);
  }, [mounted]);

  const stopAnim = useCallback(() => {
    if (animRef.current !== null) {
      cancelAnimationFrame(animRef.current);
      animRef.current = null;
    }
  }, []);
  useEffect(() => stopAnim, [stopAnim]);

  // rAF-coalesced k updates: a fast wheel emits many move events per frame;
  // one re-render per frame is all the marker layer needs.
  const pendingK = useRef<number | null>(null);
  const kFrame = useRef<number | null>(null);
  const handleMove = useCallback(({ zoom }: { x: number; y: number; zoom: number }) => {
    pendingK.current = zoom;
    if (kFrame.current === null) {
      kFrame.current = requestAnimationFrame(() => {
        kFrame.current = null;
        if (pendingK.current !== null) setK(pendingK.current);
      });
    }
    setTransformed(true);
  }, []);
  useEffect(
    () => () => {
      if (kFrame.current !== null) cancelAnimationFrame(kFrame.current);
    },
    [],
  );

  const handleMoveEnd = useCallback(
    (pos: { coordinates: [number, number]; zoom: number }) => {
      stopAnim();
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
    [defaultCenter, onUserViewChange, stopAnim],
  );

  /** Glide from the current view to the target (Airbnb-style easing) instead
   *  of teleporting. Zoom interpolates in log space so a 2x→8x flight feels
   *  linear to the eye. Honors prefers-reduced-motion by jumping. */
  const flyTo = useCallback(
    (coordinates: [number, number], zoom: number) => {
      const z = Math.max(1, Math.min(MAX_ZOOM, zoom));
      stopAnim();
      const reduced =
        typeof window !== "undefined" &&
        window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      const from = positionRef.current;
      if (reduced || !Number.isFinite(from.zoom)) {
        setPosition({ coordinates, zoom: z });
        setK(z);
        return;
      }
      const fromLogZ = Math.log(from.zoom);
      const toLogZ = Math.log(z);
      const start = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / ZOOM_TWEEN_MS);
        const e = easeCubicOut(t);
        const zoomNow = Math.exp(fromLogZ + (toLogZ - fromLogZ) * e);
        const next: Position = {
          coordinates: [
            from.coordinates[0] + (coordinates[0] - from.coordinates[0]) * e,
            from.coordinates[1] + (coordinates[1] - from.coordinates[1]) * e,
          ],
          zoom: zoomNow,
        };
        setPosition(next);
        setK(zoomNow);
        if (t < 1) {
          animRef.current = requestAnimationFrame(step);
        } else {
          animRef.current = null;
        }
      };
      animRef.current = requestAnimationFrame(step);
    },
    [stopAnim],
  );

  const reset = useCallback(() => {
    flyTo(defaultCenter, 1);
    setTransformed(false);
  }, [defaultCenter, flyTo]);

  const zoomTo = useCallback(
    (coordinates: [number, number], zoom: number) => {
      flyTo(coordinates, zoom);
      setTransformed(true);
    },
    [flyTo],
  );

  useEffect(() => {
    if (!apiRef) return;
    apiRef.current = { zoomTo, reset };
    return () => {
      apiRef.current = null;
    };
  }, [apiRef, zoomTo, reset]);

  // Default filter blocks ctrlKey events, which is what trackpad pinches
  // arrive as — allow everything except non-primary buttons. MUST be a
  // stable identity: react-simple-maps re-creates and re-binds the whole
  // d3-zoom behavior whenever this prop changes, and an inline arrow gave
  // it a new identity every render — rebinding zoom MID-GESTURE, which is
  // exactly the "zoom feels broken" bug.
  const filterZoomEvent = useCallback((evt: unknown) => {
    const e = evt as { button?: number };
    return !e.button;
  }, []);

  // Geographies re-render only when k crosses a half-step bucket.
  const kBucket = Math.max(1, Math.round(k * 2) / 2);

  if (!mounted) {
    // Same box, quiet placeholder — the topo JSON fetch already keeps the
    // real map from painting for a beat, so this adds no perceived delay.
    return <div className="relative h-full w-full" aria-hidden />;
  }

  return (
    // Fills whatever box the caller gives it. The caller owns the height so a
    // sibling panel can never drive the map's size.
    <div
      ref={containerRef}
      className="relative h-full w-full cursor-grab active:cursor-grabbing"
      style={{ touchAction: "none", overscrollBehavior: "contain" }}
    >
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
          maxZoom={MAX_ZOOM}
          translateExtent={[
            [0, 0],
            [MAP_WIDTH, MAP_HEIGHT],
          ]}
          filterZoomEvent={filterZoomEvent}
          onMove={handleMove}
          onMoveEnd={handleMoveEnd}
        >
          <BaseGeographies kBucket={kBucket} />
          {children({ k, projection })}
        </ZoomableGroup>
      </ComposableMap>
    </div>
  );
}
