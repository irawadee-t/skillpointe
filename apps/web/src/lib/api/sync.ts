/**
 * SKILLED Nation <-> Pro sync console (admin).
 * Backend: apps/api/app/routers/sync.py
 */
import { apiFetch } from "./client";

export interface RecentEvent {
  event_id: string;
  aggregate_type: string;
  event_type: string;
  source: string;
  occurred_at: string;
  published: boolean;
}

export interface SyncStatus {
  outbox_unpublished: number;
  outbox_total: number;
  inbox_total: number;
  stream_depth: number;
  pending: number;
  in_sync: boolean;
  recent: RecentEvent[];
}

export type PartnerStatus = "healthy" | "delayed" | "down";

export interface PartnerHealth {
  source: string;
  name: string;
  status: PartnerStatus;
  last_sync_at: string | null;
  events_24h: number;
  backlog: number;
  oldest_pending_at: string | null;
}

export interface StuckEvent {
  event_id: string;
  partner: string;
  source: string;
  event_type: string;
  aggregate_type: string;
  occurred_at: string;
  waiting_seconds: number;
}

export interface PartnerHealthResponse {
  partners: PartnerHealth[];
  stuck: StuckEvent[];
  total_backlog: number;
  total_events_24h: number;
}

export interface PublishResult { published: number; }
export interface ConsumeResult { consumed: number; applied: number; duplicates: number; skipped: number; }
export interface ReconcileResult {
  published: number;
  applied: number;
  missing_in_inbox: string[];
  extra_in_inbox: string[];
  in_sync: boolean;
}
export interface EmitResult { emitted: number; event_ids: string[]; }

export const getSyncStatus = (token: string) =>
  apiFetch<SyncStatus>("/admin/sync/status", token);

export const getPartnerHealth = (token: string) =>
  apiFetch<PartnerHealthResponse>("/admin/sync/partners", token);

export const publishEvents = (token: string) =>
  apiFetch<PublishResult>("/admin/sync/publish", token, { method: "POST" });

export const consumeEvents = (token: string) =>
  apiFetch<ConsumeResult>("/admin/sync/consume", token, { method: "POST" });

export const reconcileSync = (token: string) =>
  apiFetch<ReconcileResult>("/admin/sync/reconcile", token, { method: "POST" });

export const emitEvent = (token: string, body: { event_type?: string; source?: string; count?: number }) =>
  apiFetch<EmitResult>("/admin/sync/emit", token, { method: "POST", body: JSON.stringify(body) });
