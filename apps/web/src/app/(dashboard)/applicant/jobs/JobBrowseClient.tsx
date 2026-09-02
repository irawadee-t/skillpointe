"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  MapPin,
  Building2,
  ExternalLink,
  Briefcase,
  Check,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  List,
  LocateFixed,
  Map as MapIcon,
} from "lucide-react";

import { motion, AnimatePresence } from "motion/react";

import type { BrowseScope, JobBrowseItem, JobBrowseResponse, JobPinsResponse } from "./page";
import { RADIUS_PRESETS } from "./radius";
import { JobSections } from "@/components/jobs/JobSections";
import { ApplySheet } from "@/components/applicant/ApplySheet";
import { consumeApplyReturn, peekApplyReturn } from "@/lib/applyReturn";
import { apiFetch } from "@/lib/api/client";
import { listMyApplications } from "@/lib/api/transactions";
import { zoomForRadiusMiles } from "@/lib/mapCluster";
import { bboxParam, viewportBbox, type MapView } from "@/lib/mapViewport";
import { PageHeader, SearchSuggestField, Stagger, StaggerItem, UrlSelectField } from "@/components/ui";
import { easeCohere } from "@/lib/motion";
import { cn } from "@/lib/utils";

/** The map pane is heavy (topojson + d3) — load it client-side only with a
 *  quiet skeleton so the split layout never shifts. */
const JobsMap = dynamic(
  () => import("@/components/jobs/JobsMap").then((m) => m.JobsMap),
  {
    ssr: false,
    loading: () => (
      <div aria-busy="true" aria-label="Loading map" className="h-full w-full bg-stone/50" />
    ),
  },
);

/** Per-job applied state, loaded once and updated optimistically on apply. */
interface AppliedInfo {
  id: string;
  status: string;
  when: string; // display string, e.g. "Jul 12" or "Just now"
}


const US_STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
  "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
  "VA","WA","WV","WI","WY",
];

const WORK_SETTING_LABELS: Record<string, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  on_site: "On-site",
  flexible: "Flexible",
};

interface Props {
  data: JobBrowseResponse | null;
  fetchError: string | null;
  currentPage: number;
  q: string;
  tradeFilter: string;
  stateFilter: string;
  workSetting: string;
  employerFilter: string;
  employers: string[];
  trades: { value: string; label: string }[];
  token: string;
  /** Map payload — ALL jobs matching the current filters (not just this page). */
  pins: JobPinsResponse | null;
  /** The active geographic scope the SERVER resolved from the URL. */
  scope: BrowseScope;
  /** The viewport applied server-side when scope is "map" (URL bbox, or the
   *  default framing around the profile location). */
  bbox: { minLng: number; minLat: number; maxLng: number; maxLat: number } | null;
  /** Map scope: jobs without coordinates are appended to the list. */
  includeUnmapped: boolean;
  /** Initial map framing for the map scope (restored URL view or the default
   *  local view); null outside the map scope. */
  initialView: MapView | null;
  radiusMi: number | null;
  /** Resolved center when the radius filter is active. */
  center: { lat: number; lng: number } | null;
  locSource: "device" | "profile" | null;
  profileCity: string | null;
  profileState: string | null;
  profileHasCoords: boolean;
}

export function JobBrowseClient({
  data,
  fetchError,
  currentPage,
  q,
  tradeFilter,
  stateFilter,
  workSetting,
  employerFilter,
  employers,
  trades,
  token,
  pins,
  scope,
  includeUnmapped,
  initialView,
  radiusMi,
  center,
  locSource,
  profileCity,
  profileState,
  profileHasCoords,
}: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  // Debounced callbacks read the CURRENT params, not the ones captured when
  // the debounce was scheduled.
  const searchParamsRef = useRef(searchParams);
  searchParamsRef.current = searchParams;

  // ----- Viewport-driven refetch (search as you move the map) -----
  // Panning/zooming fetches list + pins for the new viewport CLIENT-side (the
  // old list stays up while the new one loads) and mirrors the bbox into the
  // URL with history.replaceState, so refresh/back restores the exact view.
  // Any server payload (filters, pills, pagination — full route transitions)
  // supersedes the override; the effect below clears it.
  const [live, setLive] = useState<{ data: JobBrowseResponse; pins: JobPinsResponse | null } | null>(null);
  const [viewportLoading, setViewportLoading] = useState(false);
  const [viewportError, setViewportError] = useState(false);
  const [searchAsMove, setSearchAsMove] = useState(true);
  const [movedSinceApply, setMovedSinceApply] = useState(false);
  const lastUserViewRef = useRef<MapView | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    abortRef.current?.abort();
    window.clearTimeout(debounceRef.current);
    setLive(null);
    setViewportLoading(false);
    setViewportError(false);
  }, [data, pins]);
  useEffect(
    () => () => {
      abortRef.current?.abort();
      window.clearTimeout(debounceRef.current);
    },
    [],
  );

  const applyViewport = useCallback(
    async (v: MapView) => {
      const box = viewportBbox(v);
      if (!box) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setViewportLoading(true);
      setViewportError(false);

      const sp = searchParamsRef.current;
      const filterQs = new URLSearchParams();
      for (const key of ["q", "trade", "state", "employer", "work_setting"]) {
        const value = sp.get(key);
        if (value) filterQs.set(key, value);
      }
      filterQs.set("bbox", bboxParam(box));
      if (sp.get("unmapped") === "1") filterQs.set("include_unmapped", "true");
      const listQs = new URLSearchParams(filterQs);
      listQs.set("page", "1");
      listQs.set("per_page", "24");

      const [listResult, pinsResult] = await Promise.allSettled([
        apiFetch<JobBrowseResponse>(`/jobs/browse?${listQs.toString()}`, token, {
          signal: controller.signal,
        }),
        apiFetch<JobPinsResponse>(`/jobs/browse/pins?${filterQs.toString()}`, token, {
          signal: controller.signal,
        }),
      ]);
      if (controller.signal.aborted) return; // a newer viewport superseded this one
      if (listResult.status !== "fulfilled") {
        setViewportLoading(false);
        setViewportError(true);
        return;
      }
      setLive({
        data: listResult.value,
        pins: pinsResult.status === "fulfilled" ? pinsResult.value : null,
      });
      setMovedSinceApply(false);
      setViewportLoading(false);

      // One scope at a time: bbox in, radius/near/page (and the explicit
      // Anywhere marker) out. replaceState keeps this a client-side move.
      const url = new URLSearchParams(sp.toString());
      url.set("bbox", bboxParam(box));
      for (const key of ["radius", "near", "nlat", "nlng", "page", "scope"]) url.delete(key);
      window.history.replaceState(null, "", `${pathname}?${url.toString()}`);
    },
    [token, pathname],
  );

  const handleUserViewChange = useCallback(
    (v: MapView) => {
      lastUserViewRef.current = v;
      if (searchAsMove) {
        window.clearTimeout(debounceRef.current);
        debounceRef.current = window.setTimeout(() => void applyViewport(v), 400);
      } else {
        setMovedSinceApply(true);
      }
    },
    [searchAsMove, applyViewport],
  );

  const searchThisArea = useCallback(() => {
    const v = lastUserViewRef.current;
    if (!v) return;
    window.clearTimeout(debounceRef.current);
    void applyViewport(v);
  }, [applyViewport]);

  /** The scope-chip escape into map mode: adopt whatever the map shows now. */
  const useMapArea = useCallback(() => {
    const v = lastUserViewRef.current ?? initialView ?? { lng: -96.6, lat: 38.7, zoom: 1 };
    window.clearTimeout(debounceRef.current);
    void applyViewport(v);
  }, [applyViewport, initialView]);

  /** URL param updates that go through the router (server refetch). */
  const setUrlParams = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParamsRef.current.toString());
      for (const [k, v] of Object.entries(updates)) {
        if (v === null || v === "") params.delete(k);
        else params.set(k, v);
      }
      params.delete("page");
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname],
  );

  // Effective payloads/scope: the client viewport override wins until the
  // next server payload replaces it.
  const effData = live?.data ?? data;
  const effPins = live?.pins ?? pins;
  const effScope: BrowseScope = live ? "map" : scope;
  const effPage = live ? 1 : currentPage;

  const jobs = effData?.jobs ?? [];
  const total = effData?.total ?? 0;
  const totalPages = effData?.total_pages ?? 1;
  const geoActive = effScope === "radius" && radiusMi !== null && center !== null;
  // "Clear all" appears only for URL-driven choices — the default map framing
  // (no bbox in the URL) is the page's resting state, not a filter.
  const hasFilters = !!(
    q || tradeFilter || stateFilter || workSetting || employerFilter || geoActive ||
    searchParams.get("bbox") !== null || searchParams.get("scope") !== null || live
  );

  // Map framing: radius fit, the map scope's initial view, or the national
  // frame for Anywhere. Null while the user drives the map (live override).
  const mapFraming = useMemo<MapView | "national" | null>(() => {
    if (live) return null;
    if (scope === "radius" && center) {
      return { lng: center.lng, lat: center.lat, zoom: radiusMi ? zoomForRadiusMiles(radiusMi) : 4 };
    }
    if (scope === "map") return initialView;
    return "national";
  }, [live, scope, center, radiusMi, initialView]);

  // Applied overlay — which of these jobs the applicant already applied to.
  // Withdrawn applications don't show as "Applied" (one re-apply is allowed).
  const [applied, setApplied] = useState<Record<string, AppliedInfo>>({});
  useEffect(() => {
    listMyApplications(token)
      .then((apps) => {
        const map: Record<string, AppliedInfo> = {};
        for (const a of apps) {
          if (a.status === "withdrawn") continue;
          map[a.job_id] = {
            id: a.id,
            status: a.status,
            when: new Date(a.submitted_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
          };
        }
        setApplied(map);
      })
      .catch(() => { /* non-fatal — cards just show the apply buttons */ });
  }, [token]);

  // One sheet instance for the whole list; the job persists through the close
  // animation so the exit transition isn't cut short.
  const [sheetJob, setSheetJob] = useState<JobBrowseItem | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  // ----- List <-> map sync (the Airbnb pattern) -----
  // hoveredId: card under the pointer -> its pin enlarges on the map.
  // mapActiveId: pin hovered/clicked on the map -> popover + card highlight.
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [mapActiveId, setMapActiveId] = useState<string | null>(null);
  // Mobile (<lg): list OR map, toggled by the floating pill (Airbnb mobile).
  const [showMap, setShowMap] = useState(false);

  const listIds = new Set(jobs.map((j) => j.job_id));

  const prefersReducedMotion = useRef(false);
  useEffect(() => {
    prefersReducedMotion.current =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  }, []);

  const viewInList = useCallback((id: string) => {
    setMapActiveId(id);
    setShowMap(false); // mobile: jump back to the list view
    // Wait a frame so the list is visible before scrolling (mobile toggle).
    requestAnimationFrame(() => {
      document.getElementById(`job-card-${id}`)?.scrollIntoView({
        block: "center",
        behavior: prefersReducedMotion.current ? "auto" : "smooth",
      });
    });
  }, []);

  // Return-trip honor: if the user left this page for /applicant/credentials
  // from a job's apply sheet, reopen that job's sheet when they come back.
  useEffect(() => {
    if (jobs.length === 0) return;
    const pending = peekApplyReturn();
    if (!pending) return;
    const job = jobs.find((j) => j.job_id === pending.jobId);
    if (!job) return; // different page/filters — the sheet self-opens where that job mounts
    consumeApplyReturn(pending.jobId);
    setSheetJob(job);
    setSheetOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs.length]);

  const nearLabel = geoActive
    ? locSource === "device"
      ? "you"
      : [profileCity, profileState].filter(Boolean).join(", ") || "your profile location"
    : null;

  // The count line is truthful to the ACTIVE scope. In map scope it also
  // carries the honest unmapped story: jobs without coordinates cannot be
  // placed in or out of a viewport, so they are excluded with a count and a
  // one-click way back in.
  const withoutCoords = effPins?.without_coords ?? 0;
  const mappedTotal = includeUnmapped ? Math.max(0, total - withoutCoords) : total;
  const unmappedToggle = (label: string, on: boolean) => (
    <button
      type="button"
      onClick={() => setUrlParams({ unmapped: on ? null : "1" })}
      className="underline decoration-hairline underline-offset-2 transition-colors hover:text-ink"
    >
      {label}
    </button>
  );
  const lead =
    effScope === "map" ? (
      includeUnmapped && withoutCoords > 0 ? (
        <>
          {total.toLocaleString()} job{total !== 1 ? "s" : ""} · {mappedTotal.toLocaleString()} in
          this area · {withoutCoords.toLocaleString()} without a mapped location{" "}
          {unmappedToggle("Hide them", true)}
        </>
      ) : (
        <>
          {total.toLocaleString()} job{total !== 1 ? "s" : ""} in this area
          {withoutCoords > 0 && (
            <>
              {" "}· {withoutCoords.toLocaleString()} more without a mapped location{" "}
              {unmappedToggle("Show them", false)}
            </>
          )}
        </>
      )
    ) : geoActive ? (
      `${total.toLocaleString()} job${total !== 1 ? "s" : ""} within ${radiusMi} mi of ${nearLabel}`
    ) : (
      `${total.toLocaleString()} skilled trade${total !== 1 ? "s" : ""} position${total !== 1 ? "s" : ""} available`
    );

  return (
    <main className="py-8">
      <div className="page-shell space-y-6">
        <PageHeader eyebrow="Browse" title="Browse jobs" lead={lead} />

        {/* Live type-ahead — results narrow with every letter typed.
            The filter bar spans BOTH panes; every control here updates the
            list and the map pins together. */}
        <div className="bg-white border border-border-light rounded-md p-4 space-y-3">
          {/* As-you-type suggestions (titles / employers / trades over active
              jobs). Picking a job title applies it to q; an employer or trade
              routes to its own filter param (predicate parity — q does not
              match employer names on this surface). Typing without picking
              live-filters exactly as before. */}
          <SearchSuggestField
            param="q"
            suggest="jobs-browse"
            placeholder="Search by title or description..."
            inputClassName="pl-10"
            paramForKind={{ employer: "employer", trade: "trade" }}
            pickValue={(item) =>
              item.kind === "trade"
                ? (trades.find((t) => t.label === item.label)?.value ?? item.label)
                : item.label
            }
          />
          <div className="flex flex-wrap gap-3 pt-2 border-t border-border-light">
            <UrlSelectField
              param="trade"
              selectClassName="w-auto rounded-sm border border-hairline bg-white px-3 py-1.5 text-caption text-ink transition-colors focus:outline-none focus:border-focus-violet focus:ring-1 focus:ring-focus-violet/40"
              options={[{ value: "", label: "All trades" }, ...trades]}
            />
            <UrlSelectField
              param="employer"
              selectClassName="w-auto rounded-sm border border-hairline bg-white px-3 py-1.5 text-caption text-ink transition-colors focus:outline-none focus:border-focus-violet focus:ring-1 focus:ring-focus-violet/40"
              options={[{ value: "", label: "All employers" }, ...employers.map((e) => ({ value: e, label: e }))]}
            />
            <UrlSelectField
              param="state"
              selectClassName="w-auto rounded-sm border border-hairline bg-white px-3 py-1.5 text-caption text-ink transition-colors focus:outline-none focus:border-focus-violet focus:ring-1 focus:ring-focus-violet/40"
              options={[{ value: "", label: "All states" }, ...US_STATES.map((s) => ({ value: s, label: s }))]}
            />
            <UrlSelectField
              param="work_setting"
              selectClassName="w-auto rounded-sm border border-hairline bg-white px-3 py-1.5 text-caption text-ink transition-colors focus:outline-none focus:border-focus-violet focus:ring-1 focus:ring-focus-violet/40"
              options={[
                { value: "", label: "All work settings" },
                { value: "on_site", label: "On-site" },
                { value: "remote", label: "Remote" },
                { value: "hybrid", label: "Hybrid" },
                { value: "flexible", label: "Flexible" },
              ]}
            />
            {hasFilters && (
              <Link href="/applicant/jobs" className="flex items-center gap-1 text-micro text-slate-muted hover:text-ink self-center ml-auto transition-colors">
                Clear all
              </Link>
            )}
          </div>

          <RadiusControl
            scope={effScope}
            radiusMi={radiusMi}
            locSource={locSource}
            profileCity={profileCity}
            profileState={profileState}
            profileHasCoords={profileHasCoords}
            onUseMapArea={useMapArea}
          />
        </div>

        {/* Split view — list left, sticky map right (Airbnb). Below lg the
            floating pill toggles between full-width list and full-bleed map. */}
        <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,44%)] lg:items-start lg:gap-6">
          {/* ---- List pane ---- */}
          <div className={cn("min-w-0 space-y-6", showMap && "hidden lg:block")}>
            {fetchError && (
              <div className="bg-studio-maroon/[0.06] border border-studio-maroon/30 rounded-md p-5 text-body text-cohere-ink">{fetchError}</div>
            )}

            {!fetchError && jobs.length === 0 && (
              <div className="bg-stone border border-transparent rounded-md p-10 text-center">
                <Briefcase className="w-8 h-8 text-slate mx-auto" />
                <p className="text-[1.0625rem] font-medium text-cohere-ink mt-3">
                  {effScope === "map"
                    ? "No jobs in this area"
                    : geoActive
                      ? `No jobs within ${radiusMi} mi`
                      : q
                        ? <>No results for &ldquo;{q}&rdquo;</>
                        : "No jobs found"}
                </p>
                <p className="text-body text-slate mt-1">
                  {effScope === "map"
                    ? "Zoom out to widen the search, or pick Anywhere."
                    : geoActive
                      ? "Try widening the radius."
                      : "Try adjusting your search or filters."}
                </p>
              </div>
            )}

            {jobs.length > 0 && (
              <Stagger className="space-y-3">
                {jobs.map((job) => (
                  <StaggerItem key={job.job_id}>
                    <ExpandableJobCard
                      job={job}
                      token={token}
                      applied={applied[job.job_id]}
                      geoActive={geoActive}
                      highlighted={mapActiveId === job.job_id}
                      onHoverChange={(over) =>
                        setHoveredId((prev) =>
                          over ? job.job_id : prev === job.job_id ? null : prev,
                        )
                      }
                      onApply={() => { setSheetJob(job); setSheetOpen(true); }}
                    />
                  </StaggerItem>
                ))}
              </Stagger>
            )}

            {totalPages > 1 && (
              <div className="flex items-center justify-between bg-white border border-border-light rounded-md px-4 py-3">
                <p className="text-body text-slate">
                  Page {effPage} of {totalPages} ({total.toLocaleString()} total)
                </p>
                <div className="flex gap-2">
                  {effPage > 1 && (
                    <PaginationLink page={effPage - 1} label="Previous" icon="left" />
                  )}
                  {effPage < totalPages && (
                    <PaginationLink page={effPage + 1} label="Next" icon="right" />
                  )}
                </div>
              </div>
            )}
          </div>

          {/* ---- Map pane — sticky beside the scrolling list ---- */}
          <div className={cn("lg:sticky lg:top-6 lg:block", showMap ? "block" : "hidden")}>
            <div className="relative h-[calc(100dvh-15rem)] min-h-[420px] overflow-hidden rounded-[14px] border border-hairline bg-white lg:h-[calc(100vh-3rem)]">
              {effPins ? (
                <JobsMap
                  pins={effPins.pins}
                  totalPins={effPins.total}
                  withoutCoords={effPins.without_coords}
                  center={live ? null : center}
                  radiusMiles={!live && geoActive ? radiusMi : null}
                  framing={mapFraming}
                  onUserViewChange={handleUserViewChange}
                  showUnmappedNote={effScope !== "map"}
                  hoveredId={hoveredId}
                  activeId={mapActiveId}
                  onActivate={setMapActiveId}
                  onViewInList={viewInList}
                  listIds={listIds}
                />
              ) : (
                <div className="flex h-full items-center justify-center">
                  <p className="text-caption text-slate-muted">
                    The map couldn&rsquo;t load. The list is unaffected.
                  </p>
                </div>
              )}

              {/* Search-as-you-move control — a fixed-size slot so swapping the
                  checkbox chip for the "Search this area" button never shifts
                  anything. */}
              <div className="absolute left-3 top-3 z-[2] flex h-8 items-center">
                {!searchAsMove && movedSinceApply ? (
                  <button
                    type="button"
                    onClick={searchThisArea}
                    className="flex h-8 items-center rounded-full border border-hairline bg-white px-3 text-caption font-medium text-ink shadow-float transition-colors hover:border-cohere-ink"
                  >
                    Search this area
                  </button>
                ) : (
                  <label className="flex h-8 cursor-pointer items-center gap-2 rounded-full border border-hairline bg-white/95 px-3 text-caption text-slate">
                    <input
                      type="checkbox"
                      checked={searchAsMove}
                      onChange={(e) => {
                        setSearchAsMove(e.target.checked);
                        if (e.target.checked && movedSinceApply && lastUserViewRef.current) {
                          void applyViewport(lastUserViewRef.current);
                        }
                      }}
                      className="h-3.5 w-3.5 accent-ink"
                    />
                    Search as I move the map
                  </label>
                )}
              </div>

              {/* Quiet status chips — absolutely positioned, so appearing and
                  disappearing never shifts the layout. */}
              {viewportLoading && (
                <div className="pointer-events-none absolute left-1/2 top-3 z-[2] -translate-x-1/2">
                  <span className="rounded-full border border-hairline bg-white/95 px-3 py-1 text-micro text-slate-muted">
                    Updating the list…
                  </span>
                </div>
              )}
              {viewportError && !viewportLoading && (
                <div className="pointer-events-none absolute left-1/2 top-3 z-[2] -translate-x-1/2">
                  <span className="rounded-full border border-hairline bg-white/95 px-3 py-1 text-micro text-slate-muted">
                    The list couldn&rsquo;t update for this area. Move the map to retry.
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {sheetJob && (
          <ApplySheet
            token={token}
            jobId={sheetJob.job_id}
            jobTitle={sheetJob.title}
            open={sheetOpen}
            onClose={() => setSheetOpen(false)}
            onApplied={(app) =>
              setApplied((prev) => ({
                ...prev,
                [sheetJob.job_id]: { id: app.id, status: app.status, when: "Just now" },
              }))
            }
          />
        )}
      </div>

      {/* Mobile map/list toggle — Airbnb's floating pill */}
      <button
        type="button"
        onClick={() => setShowMap((v) => !v)}
        className="fixed bottom-6 left-1/2 z-30 flex -translate-x-1/2 items-center gap-2 rounded-full bg-ink px-4 py-2.5 text-caption font-medium text-white shadow-float lg:hidden"
        aria-pressed={showMap}
      >
        {showMap ? (
          <>
            <List className="h-4 w-4" aria-hidden /> Show list
          </>
        ) : (
          <>
            <MapIcon className="h-4 w-4" aria-hidden /> Show map
          </>
        )}
      </button>
    </main>
  );
}

/**
 * "Near me" + radius pills + the scope chips — the geo row. Radius and
 * location source persist in the URL (radius=50&near=profile, or near=device
 * with nlat/nlng rounded to ~1 km before they touch the URL; profile
 * coordinates never enter the URL — the server resolves them). Exactly one
 * geographic scope is active at a time: a radius pill, "Map area" (the
 * viewport, bbox in the URL), or "Anywhere". Picking any of the three clears
 * the other two, and the pressed pill always shows which one is live.
 */
function RadiusControl({
  scope,
  radiusMi,
  locSource,
  profileCity,
  profileState,
  profileHasCoords,
  onUseMapArea,
}: {
  scope: BrowseScope;
  radiusMi: number | null;
  locSource: "device" | "profile" | null;
  profileCity: string | null;
  profileState: string | null;
  profileHasCoords: boolean;
  onUseMapArea: () => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [locating, setLocating] = useState(false);
  const [geoNote, setGeoNote] = useState<string | null>(null);

  // Any radius/Anywhere pick leaves the map-area scope behind.
  const CLEAR_MAP_SCOPE: Record<string, string | null> = {
    bbox: null,
    unmapped: null,
    scope: null,
  };

  const setParams = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [k, v] of Object.entries(updates)) {
        if (v === null || v === "") params.delete(k);
        else params.set(k, v);
      }
      params.delete("page");
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname, searchParams],
  );

  const requestDeviceLocation = useCallback(
    (withRadius: number) => {
      if (!("geolocation" in navigator)) {
        setGeoNote(
          profileHasCoords
            ? "Location isn't available in this browser. Using your profile location instead."
            : "Location isn't available in this browser, and your profile has no city yet.",
        );
        if (profileHasCoords) {
          setParams({
            ...CLEAR_MAP_SCOPE,
            near: "profile", radius: String(withRadius), nlat: null, nlng: null,
          });
        }
        return;
      }
      setLocating(true);
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setLocating(false);
          setGeoNote(null);
          // ~1 km precision is plenty for a 10+ mile radius and keeps exact
          // coordinates out of the URL.
          setParams({
            ...CLEAR_MAP_SCOPE,
            near: "device",
            nlat: pos.coords.latitude.toFixed(2),
            nlng: pos.coords.longitude.toFixed(2),
            radius: String(withRadius),
          });
        },
        () => {
          setLocating(false);
          if (profileHasCoords) {
            setGeoNote(
              `Location access was denied. Using your profile location${
                profileCity ? ` (${[profileCity, profileState].filter(Boolean).join(", ")})` : ""
              } instead.`,
            );
            setParams({
              ...CLEAR_MAP_SCOPE,
              near: "profile", radius: String(withRadius), nlat: null, nlng: null,
            });
          } else {
            setGeoNote(
              "Location access was denied, and your profile has no city yet. Add one on your profile page to filter by distance.",
            );
          }
        },
        { timeout: 10_000, maximumAge: 300_000 },
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [profileHasCoords, profileCity, profileState, setParams],
  );

  const pickRadius = (r: number | null) => {
    setGeoNote(null);
    if (r === null) {
      // "Anywhere" — the explicit escape hatch: national list, national map.
      // Location source stays so re-picking a radius reuses it; scope=anywhere
      // also suppresses the default start-near-your-profile framing.
      setParams({ ...CLEAR_MAP_SCOPE, radius: null, scope: "anywhere" });
      return;
    }
    if (locSource !== null) {
      setParams({ ...CLEAR_MAP_SCOPE, radius: String(r) });
    } else if (profileHasCoords) {
      setParams({ ...CLEAR_MAP_SCOPE, radius: String(r), near: "profile" });
    } else {
      requestDeviceLocation(r);
    }
  };

  const radiusActive = scope === "radius";
  const sourceLabel =
    locSource === "device"
      ? "Using your device location"
      : locSource === "profile"
        ? `Using your profile location${
            profileCity ? ` (${[profileCity, profileState].filter(Boolean).join(", ")})` : ""
          }`
        : null;

  const pillClass = (active: boolean) =>
    cn(
      "rounded-full border px-3 py-1.5 text-caption transition-colors",
      active
        ? "border-ink bg-ink text-white"
        : "border-hairline bg-white text-slate hover:border-cohere-ink hover:text-ink",
    );

  return (
    <div className="space-y-2 border-t border-border-light pt-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => requestDeviceLocation(radiusMi ?? 50)}
          disabled={locating}
          aria-pressed={radiusActive && locSource === "device"}
          className={cn(
            "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-caption transition-colors",
            radiusActive && locSource === "device"
              ? "border-ink bg-ink text-white"
              : "border-hairline bg-white text-slate hover:border-cohere-ink hover:text-ink",
            locating && "opacity-60",
          )}
        >
          <LocateFixed className="h-3.5 w-3.5" aria-hidden />
          {locating ? "Locating…" : "Near me"}
        </button>

        <span className="text-micro text-slate-muted">Within</span>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Search scope">
          {RADIUS_PRESETS.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => pickRadius(r)}
              aria-pressed={radiusActive && radiusMi === r}
              className={pillClass(radiusActive && radiusMi === r)}
            >
              {r} mi
            </button>
          ))}
          <button
            type="button"
            onClick={() => pickRadius(null)}
            aria-pressed={scope === "none"}
            className={pillClass(scope === "none")}
          >
            Anywhere
          </button>
          <button
            type="button"
            onClick={() => {
              if (scope !== "map") onUseMapArea();
            }}
            aria-pressed={scope === "map"}
            title="Scope the list to what the map shows"
            className={pillClass(scope === "map")}
          >
            Map area
          </button>
        </div>

        {sourceLabel && radiusActive && (
          <span className="flex items-center gap-1 text-micro text-slate-muted">
            <MapPin className="h-3 w-3" aria-hidden />
            {sourceLabel}
            {locSource === "device" && profileHasCoords && (
              <button
                type="button"
                onClick={() => setParams({ near: "profile", nlat: null, nlng: null })}
                className="ml-1 underline decoration-hairline underline-offset-2 hover:text-ink"
              >
                use profile location
              </button>
            )}
          </span>
        )}
      </div>
      {geoNote && <p className="text-micro text-slate-muted">{geoNote}</p>}
      {!profileHasCoords && scope === "none" && !geoNote && (
        <p className="text-micro text-slate-muted">
          Add your city in your profile to start the map near you.
        </p>
      )}
    </div>
  );
}

function PaginationLink({ page, label, icon }: {
  page: number; label: string; icon: "left" | "right";
}) {
  // Preserve EVERY active filter (incl. radius/near) — only the page changes.
  const searchParams = useSearchParams();
  const qs = new URLSearchParams(searchParams.toString());
  qs.set("page", String(page));
  return (
    <Link href={`/applicant/jobs?${qs.toString()}`} className="flex items-center gap-1 px-3 py-1.5 border border-hairline rounded-pill text-caption text-slate hover:border-cohere-ink hover:text-ink transition-colors">
      {icon === "left" && <ChevronLeft className="w-3.5 h-3.5" />}
      {label}
      {icon === "right" && <ChevronRight className="w-3.5 h-3.5" />}
    </Link>
  );
}

function ExpandableJobCard({ job, token, applied, geoActive, highlighted, onHoverChange, onApply }: {
  job: JobBrowseItem;
  token: string;
  applied?: AppliedInfo;
  /** A distance filter is active — cards say "~18 mi" or "no mapped location". */
  geoActive: boolean;
  /** This job's pin is active on the map — mirror the emphasis here. */
  highlighted: boolean;
  onHoverChange: (hovering: boolean) => void;
  onApply: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const searchParams = useSearchParams();

  // The trade chip is a real filter: clicking it narrows the browse view to
  // this job family (URL-synced like the filter-bar selects; page resets).
  const tradeHref = (() => {
    if (!job.canonical_job_family_code) return null;
    const params = new URLSearchParams(searchParams.toString());
    params.set("trade", job.canonical_job_family_code);
    params.delete("page");
    return `/applicant/jobs?${params.toString()}`;
  })();

  // Scraped feeds sometimes send literal "Unspecified" — treat it as absent.
  const clean = (v: string | null | undefined) =>
    v && v.trim() && !/^unspecified$/i.test(v.trim()) ? v.trim() : null;
  const location = [clean(job.city), clean(job.state)].filter(Boolean).join(", ");
  const workLabel = job.work_setting ? (WORK_SETTING_LABELS[job.work_setting] ?? job.work_setting) : null;
  const payDisplay = formatPay(job);
  const hasDetail = !!(job.description || job.qualifications || job.requirements);
  const familyLabel = job.canonical_job_family_code
    ? job.canonical_job_family_code.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
    : null;

  return (
    <div
      id={`job-card-${job.job_id}`}
      onMouseEnter={() => onHoverChange(true)}
      onMouseLeave={() => onHoverChange(false)}
      className={cn(
        "rounded-[14px] border bg-white transition-[color,background-color,border-color,box-shadow,transform] duration-200 ease-cohere hover:border-cohere-ink hover:shadow-float hover:-translate-y-[2px] motion-reduce:hover:translate-y-0",
        highlighted ? "border-cohere-ink shadow-float -translate-y-[2px] motion-reduce:translate-y-0" : "border-hairline",
      )}
    >
      <div className="p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h3 className="text-[1.1875rem] font-medium text-cohere-ink leading-snug">{job.title}</h3>
            <p className="text-body text-slate mt-0.5 flex items-center gap-1">
              <Building2 className="w-3.5 h-3.5 shrink-0" />
              {job.employer_name}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {applied ? (
              <Link
                href={`/applicant/applications/${applied.id}`}
                className="inline-flex items-center gap-1 rounded-full border border-cohere-green bg-cohere-green px-3 py-1 text-caption font-medium text-white"
              >
                <Check className="w-3.5 h-3.5 text-white" /> Applied · {applied.when}
              </Link>
            ) : job.internal_apply ? (
              <button
                onClick={onApply}
                className="btn-commit !px-4 !py-1.5 text-caption transition-transform duration-100 active:scale-[0.97]"
              >
                Apply
              </button>
            ) : job.source_url ? (
              <a href={job.source_url} target="_blank" rel="noopener noreferrer"
                className="btn-sm">
                Apply <ExternalLink className="w-3 h-3" />
              </a>
            ) : null}
            {hasDetail && (
              <button onClick={() => setExpanded(!expanded)}
                className="p-1.5 rounded-sm border border-hairline text-slate hover:text-ink hover:border-cohere-ink transition-colors"
                aria-label={expanded ? "Collapse details" : "Expand details"}>
                {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-body text-slate">
          {(location || workLabel) && (
            <span className="flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5 shrink-0 text-slate" />
              {[location, workLabel].filter(Boolean).join(", ")}
            </span>
          )}
          {/* Distance from the active center — honest: absent coordinates say so. */}
          {job.distance_miles !== null && (
            <span className="tabular-nums">
              {job.distance_miles < 1 ? "<1 mi" : `~${Math.round(job.distance_miles)} mi`}
            </span>
          )}
          {geoActive && job.distance_miles === null && (
            <span className="text-slate-muted">No mapped location</span>
          )}
          {/* payDisplay carries its own "$" — no icon, or it reads "$ $31". */}
          {payDisplay && <span>{payDisplay}</span>}
        </div>

        {!expanded && job.description_preview && (
          <p className="mt-2 text-caption text-slate line-clamp-2">
            {job.description_preview.trim()}
            {/[.!?…]$/.test(job.description_preview.trim()) ? "" : "…"}
          </p>
        )}

        {familyLabel && tradeHref && (
          <div className="mt-3">
            <Link
              href={tradeHref}
              scroll={false}
              aria-label={`Filter jobs by trade: ${familyLabel}`}
              className="rounded-sm border border-hairline bg-parchment px-2 py-0.5 text-caption text-slate transition-colors hover:border-cohere-ink hover:text-ink"
            >
              {familyLabel}
            </Link>
          </div>
        )}
      </div>

      <AnimatePresence initial={false}>
        {expanded && hasDetail && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: easeCohere }}
            className="overflow-hidden"
          >
            <div className="border-t border-border-light px-5 py-4 bg-stone space-y-5">
              <JobSections jobId={job.job_id} token={token} />
              {(job.internal_apply || job.source_url) && !applied && (
                <div className="flex flex-wrap items-center gap-2 pt-2">
                  {job.internal_apply && (
                    <button
                      onClick={onApply}
                      className="btn-commit inline-flex items-center gap-2 transition-transform duration-100 active:scale-[0.97]"
                    >
                      Apply on SKILLED Nation
                    </button>
                  )}
                  {job.source_url && (
                    <a href={job.source_url} target="_blank" rel="noopener noreferrer"
                      className={`${job.internal_apply ? "btn-ghost" : "btn-primary"} inline-flex items-center gap-2`}>
                      Apply on employer site <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                </div>
              )}
              {applied && (
                <p className="pt-2 text-caption text-cohere-ink">
                  <Check className="mr-1 inline w-3.5 h-3.5 text-cohere-green" />
                  You applied to this job · {applied.when}
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function formatPay(job: JobBrowseItem): string | null {
  if (job.pay_raw) return job.pay_raw;
  if (job.pay_min === null) return null;
  const suffix = job.pay_type === "hourly" ? "/hr" : job.pay_type === "annual" ? "/yr" : "";
  const fmt = (n: number) => job.pay_type === "annual" ? `$${(n / 1000).toFixed(0)}k` : `$${n.toFixed(0)}`;
  if (job.pay_max && job.pay_max !== job.pay_min) return `${fmt(job.pay_min)}-${fmt(job.pay_max)}${suffix}`;
  return `${fmt(job.pay_min)}${suffix}`;
}
