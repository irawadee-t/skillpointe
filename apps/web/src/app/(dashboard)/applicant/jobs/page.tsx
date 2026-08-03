import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api/client";
import type { ApplicantProfileSummary } from "@/lib/api/applicant";
import type { JobPin } from "@/components/jobs/JobsMap";
import {
  bboxParam,
  defaultLocalView,
  parseBboxParam,
  viewForBbox,
  viewportBbox,
  type GeoBbox,
  type MapView,
} from "@/lib/mapViewport";
import { JobBrowseClient } from "./JobBrowseClient";
import { RADIUS_PRESETS } from "./radius";

/** Which geographic scope the browse query is running under. Exactly one is
 *  active at a time: the map viewport (bbox), a radius circle, or none. */
export type BrowseScope = "map" | "radius" | "none";

export interface JobBrowseItem {
  job_id: string;
  title: string;
  employer_name: string;
  city: string | null;
  state: string | null;
  work_setting: string | null;
  pay_min: number | null;
  pay_max: number | null;
  pay_type: string | null;
  pay_raw: string | null;
  source: string | null;
  source_url: string | null;
  source_site: string | null;
  posted_date: string | null;
  canonical_job_family_code: string | null;
  description_preview: string | null;
  description: string | null;
  qualifications: string | null;
  requirements: string | null;
  experience_level: string | null;
  employment_type: string | null;
  /** Effective "Apply on SKILLED Nation" flag (per-job override, else company default). */
  internal_apply: boolean;
  /** Miles from the active center; null when no center or no coordinates. */
  distance_miles: number | null;
}

export interface JobBrowseResponse {
  jobs: JobBrowseItem[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface JobPinsResponse {
  pins: JobPin[];
  total: number;
  without_coords: number;
}

interface PageProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}

export default async function JobBrowsePage({ searchParams }: PageProps) {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const params = await searchParams;
  const q = typeof params.q === "string" ? params.q : "";
  const tradeFilter = typeof params.trade === "string" ? params.trade : "";
  const stateFilter = typeof params.state === "string" ? params.state : "";
  const workSetting =
    typeof params.work_setting === "string" ? params.work_setting : "";
  const employerFilter =
    typeof params.employer === "string" ? params.employer : "";
  const currentPage =
    typeof params.page === "string" ? parseInt(params.page, 10) || 1 : 1;

  // --- Geo filters (radius + location source), URL-persisted like the rest.
  // radius: one of the preset values. near: "device" (browser geolocation,
  // coords carried as nlat/nlng rounded to ~1 km by the client) or "profile"
  // (coords resolved server-side from the applicant's geocoded home city —
  // they never enter the URL).
  const radiusRaw =
    typeof params.radius === "string" ? parseInt(params.radius, 10) : NaN;
  const radiusMi = (RADIUS_PRESETS as readonly number[]).includes(radiusRaw)
    ? radiusRaw
    : null;
  const near = typeof params.near === "string" ? params.near : "";
  const nlat = typeof params.nlat === "string" ? parseFloat(params.nlat) : NaN;
  const nlng = typeof params.nlng === "string" ? parseFloat(params.nlng) : NaN;

  // Map-viewport scope: bbox=minLng,minLat,maxLng,maxLat (written by the map's
  // search-as-you-move), exclusive with the radius scope — bbox wins if both
  // somehow appear. unmapped=1 re-admits jobs without coordinates to a
  // bbox-scoped list. scope=anywhere is the explicit escape hatch that also
  // suppresses the default "start near your profile location" framing.
  const urlBbox = parseBboxParam(typeof params.bbox === "string" ? params.bbox : null);
  const includeUnmapped = params.unmapped === "1";
  const anywhere = params.scope === "anywhere";

  // Profile is non-critical for browsing, but powers the "profile location"
  // radius fallback and its label.
  let profile: ApplicantProfileSummary | null = null;
  try {
    profile = await apiFetch<ApplicantProfileSummary>(
      "/applicant/me/profile",
      session.access_token,
    );
  } catch {
    // Non-applicant sessions (admin preview) or a profile hiccup — the page
    // still browses; "Near me" falls back to device location only.
  }

  const profileHasCoords = profile?.lat != null && profile?.lng != null;

  let center: { lat: number; lng: number } | null = null;
  let locSource: "device" | "profile" | null = null;
  if (
    near === "device" &&
    Number.isFinite(nlat) &&
    Number.isFinite(nlng) &&
    Math.abs(nlat) <= 90 &&
    Math.abs(nlng) <= 180
  ) {
    center = { lat: nlat, lng: nlng };
    locSource = "device";
  } else if (profileHasCoords && (near === "profile" || radiusMi !== null)) {
    center = { lat: profile!.lat!, lng: profile!.lng! };
    locSource = "profile";
  }

  const geoActive = urlBbox === null && radiusMi !== null && center !== null;

  // Resolve the ONE active geographic scope. With no scope in the URL the
  // browse starts where the applicant is: the map frames their profile
  // coordinates at the 50 mi radius fit and the list is scoped to that same
  // viewport, so list and map agree from the first paint. "Anywhere"
  // (scope=anywhere) and profiles without coordinates fall back to national.
  let scope: BrowseScope = "none";
  let appliedBbox: GeoBbox | null = null;
  let initialView: MapView | null = null;
  if (urlBbox) {
    scope = "map";
    appliedBbox = urlBbox;
    initialView = viewForBbox(urlBbox);
  } else if (geoActive) {
    scope = "radius";
  } else if (!anywhere && profileHasCoords) {
    const localView = defaultLocalView({ lat: profile!.lat!, lng: profile!.lng! });
    const localBbox = viewportBbox(localView);
    if (localBbox) {
      scope = "map";
      appliedBbox = localBbox;
      initialView = localView;
    }
  }

  const filterQs = new URLSearchParams();
  if (q) filterQs.set("q", q);
  if (tradeFilter) filterQs.set("trade", tradeFilter);
  if (stateFilter) filterQs.set("state", stateFilter);
  if (workSetting) filterQs.set("work_setting", workSetting);
  if (employerFilter) filterQs.set("employer", employerFilter);
  if (scope === "map" && appliedBbox) {
    filterQs.set("bbox", bboxParam(appliedBbox));
    if (includeUnmapped) filterQs.set("include_unmapped", "true");
  } else if (geoActive) {
    filterQs.set("near_lat", String(center!.lat));
    filterQs.set("near_lng", String(center!.lng));
    filterQs.set("radius_miles", String(radiusMi));
  }

  const listQs = new URLSearchParams(filterQs);
  listQs.set("page", String(currentPage));
  listQs.set("per_page", "24");

  let data: JobBrowseResponse | null = null;
  let fetchError: string | null = null;
  let employers: string[] = [];
  let trades: { value: string; label: string }[] = [];
  let pins: JobPinsResponse | null = null;

  // Independent fetches — run concurrently so the page render blocks on the
  // slowest, not on their sum. Pins power the map: ALL filtered jobs, not
  // just the current page.
  const [jobsResult, pinsResult, employersResult, tradesResult] =
    await Promise.allSettled([
      apiFetch<JobBrowseResponse>(
        `/jobs/browse?${listQs.toString()}`,
        session.access_token,
      ),
      apiFetch<JobPinsResponse>(
        `/jobs/browse/pins?${filterQs.toString()}`,
        session.access_token,
      ),
      apiFetch<{ employers: string[] }>("/jobs/employers", session.access_token),
      apiFetch<{ trades: { value: string; label: string }[] }>(
        "/jobs/trades",
        session.access_token,
      ),
    ]);

  if (jobsResult.status === "fulfilled") {
    data = jobsResult.value;
  } else {
    fetchError =
      jobsResult.reason instanceof Error ? jobsResult.reason.message : "Failed to load jobs";
  }
  // Non-critical — the list still shows; the map states "couldn't load".
  if (pinsResult.status === "fulfilled") pins = pinsResult.value;
  // Non-critical — jobs still show, dropdowns fall back to empty
  if (employersResult.status === "fulfilled") {
    employers = employersResult.value.employers ?? [];
  }
  if (tradesResult.status === "fulfilled") {
    trades = tradesResult.value.trades ?? [];
  }

  return (
    <JobBrowseClient
      data={data}
      fetchError={fetchError}
      currentPage={currentPage}
      q={q}
      tradeFilter={tradeFilter}
      stateFilter={stateFilter}
      workSetting={workSetting}
      employerFilter={employerFilter}
      employers={employers}
      trades={trades}
      token={session.access_token}
      pins={pins}
      scope={scope}
      bbox={appliedBbox}
      includeUnmapped={includeUnmapped}
      initialView={initialView}
      radiusMi={scope === "radius" ? radiusMi : null}
      center={geoActive ? center : null}
      locSource={locSource}
      profileCity={profile?.city ?? null}
      profileState={profile?.state ?? null}
      profileHasCoords={profileHasCoords}
    />
  );
}
