/**
 * marketData.ts — types + fetchers for the marketplace-analytics viz pieces.
 *
 * Mirrors the Pydantic schemas of the /viz marketplace endpoints in
 * apps/api/app/routers/viz_analytics.py (supply-demand, supply-demand/geo,
 * score-distribution). Kept inside viz2/ so the marketplace pieces are
 * self-contained until the integration pass wires them into product pages.
 */
import { apiFetch } from "@/lib/api/client";

// ---------------------------------------------------------------------------
// GET /viz/supply-demand
// ---------------------------------------------------------------------------

export interface CityCount {
  city: string;
  state: string;
  count: number;
}

export interface FamilySupplyDemand {
  code: string;
  name: string;
  workers: number;
  jobs: number;
  worker_cities: CityCount[];
  job_cities: CityCount[];
}

export interface SupplyDemandResponse {
  families: FamilySupplyDemand[];
  total_workers: number;
  total_jobs: number;
}

export function fetchSupplyDemand(token: string): Promise<SupplyDemandResponse> {
  return apiFetch<SupplyDemandResponse>("/viz/supply-demand", token);
}

// ---------------------------------------------------------------------------
// GET /viz/supply-demand/geo
// ---------------------------------------------------------------------------

export interface ClusterFamily {
  code: string;
  name: string;
  workers: number;
  jobs: number;
}

export interface GeoCluster {
  key: string;
  label: string;
  lat: number;
  lng: number;
  workers: number;
  jobs: number;
  families: ClusterFamily[];
}

export interface SupplyDemandGeoResponse {
  clusters: GeoCluster[];
  cell_deg: number;
}

export function fetchSupplyDemandGeo(token: string): Promise<SupplyDemandGeoResponse> {
  return apiFetch<SupplyDemandGeoResponse>("/viz/supply-demand/geo", token);
}

// ---------------------------------------------------------------------------
// GET /viz/score-distribution
// ---------------------------------------------------------------------------

export interface ScoreBucket {
  x0: number;
  x1: number;
  count: number;
}

export interface ScoreDistributionResponse {
  total: number;
  min: number | null;
  max: number | null;
  p95: number | null;
  buckets: ScoreBucket[];
  /** moderate_fit_min / good_fit_min / strong_fit_min from the ACTIVE config. */
  thresholds: Record<string, number>;
  eligibility: Record<string, number>;
  /** One honest sentence computed server-side from the live distribution. */
  annotation: string;
}

export function fetchScoreDistribution(
  token: string,
  nbins = 50,
): Promise<ScoreDistributionResponse> {
  return apiFetch<ScoreDistributionResponse>(
    `/viz/score-distribution?nbins=${nbins}`,
    token,
  );
}
