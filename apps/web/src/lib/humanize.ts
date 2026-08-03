/**
 * humanize.ts — the ONE shared enum-humanizing helper.
 *
 * Raw enum values (stay_current, credential.verified, not_modified, …) never
 * reach the operator's screen. Every admin/product surface goes through
 * `humanizeEnum` (generic snake/dot-case → sentence case) or one of the
 * domain maps below, which win when a value needs real words rather than a
 * mechanical de-underscore.
 *
 * Usage:
 *   humanizeEnum("in_progress")                     → "In progress"
 *   humanizeEnum("stay_current", RELOCATION_LABELS) → "Prefers to stay local"
 *   humanizeEventKind("credential.verified")        → "Credential issued"
 *
 * Backend counterpart: none — humanization is presentation-only, the API
 * always speaks raw enums. Documented in DESIGN_CONTRACT.md spirit: sentence
 * case, no ALL-CAPS, no raw snake_case on screen.
 */

/** Generic fallback: snake/kebab/dot case → "Sentence case". */
export function humanizeEnum(
  value: string | null | undefined,
  overrides?: Record<string, string>,
): string {
  if (!value) return "—";
  const hit = overrides?.[value];
  if (hit) return hit;
  const words = value.replace(/[._-]+/g, " ").trim();
  if (!words) return "—";
  return words.charAt(0).toUpperCase() + words.slice(1).toLowerCase();
}

/* ── Worker preference enums (test matches, applicant views) ─────────── */
export const RELOCATION_LABELS: Record<string, string> = {
  stay_current: "Prefers to stay local",
  open_to_relocation: "Open to relocating",
  specific_states: "Open to specific states",
  anywhere: "Will go anywhere",
  unknown: "No relocation preference set",
};

export const TRAVEL_LABELS: Record<string, string> = {
  no_travel: "No travel",
  some_travel: "Open to some travel",
  frequent_travel: "Fine with frequent travel",
  unknown: "No travel preference set",
};

export const WORK_SETTING_LABELS: Record<string, string> = {
  on_site: "On-site",
  onsite: "On-site",
  remote: "Remote",
  hybrid: "Hybrid",
  flexible: "Flexible",
};

/* ── Job catalog sources ("where did this posting come from") ────────── */
// DB values as of 2026-08: scraper, seed, employer_import, plus
// employer_created written by POST /employer/me/jobs.
export const JOB_SOURCE_LABELS: Record<string, string> = {
  scraper: "Scraped",
  employer_import: "Employer import",
  employer_created: "Posted by employer",
  seed: "Demo catalog",
};

export function humanizeJobSource(source: string | null | undefined): string {
  return humanizeEnum(source, JOB_SOURCE_LABELS);
}

/* ── Sync console event kinds ("credential.verified" → "Credential issued") */
export const EVENT_KIND_LABELS: Record<string, string> = {
  "credential.verified": "Credential issued",
  "credential.revoked": "Credential revoked",
  "credential.updated": "Credential updated",
  "worker.registered": "Worker registered",
  "worker.updated": "Worker profile updated",
  "consent.granted": "Sharing consent granted",
  "consent.revoked": "Sharing consent revoked",
  "placement.reported": "Placement reported",
  "candidate.verified": "Candidate verified",
};

export function humanizeEventKind(kind: string | null | undefined): string {
  return humanizeEnum(kind, EVENT_KIND_LABELS);
}

/* ── Sync partner health ─────────────────────────────────────────────── */
export const SYNC_HEALTH_LABELS: Record<string, string> = {
  healthy: "Healthy",
  delayed: "Delayed",
  down: "Down",
  quiet: "No recent activity",
};

/* ── Career source pull statuses ─────────────────────────────────────── */
export const PULL_STATUS_LABELS: Record<string, string> = {
  ok: "Synced",
  error: "Sync failed",
  blocked: "Blocked by the site",
  partial: "Partially synced",
};

/* ── Import batch / row review states ────────────────────────────────── */
export const REVIEW_STATE_LABELS: Record<string, string> = {
  awaiting_review: "Awaiting review",
  staged_from_careers: "Staged from careers page",
  draft: "Employer editing",
  pending: "Awaiting review",
  approved: "Approved",
  rejected: "Rejected",
  published: "Published",
};

export const ROW_STATUS_LABELS: Record<string, string> = {
  staged: "Awaiting review",
  held: "Held: apply link needs fixing",
  published: "Published",
  rejected: "Rejected",
  excluded: "Excluded",
  stale: "No longer on source",
};

/* ── Review queue item types (/admin/review) ─────────────────────────── */
export const REVIEW_ITEM_TYPE_LABELS: Record<string, string> = {
  chat_guardrail: "Chat guardrail flags",
  taxonomy_mismatch: "Credential normalization",
  credential_ambiguity: "Credential ambiguity",
  extraction_confidence: "Low-confidence extraction",
  borderline_match: "Borderline matches",
  geography_ambiguity: "Geography ambiguity",
  suspicious_import: "Suspicious import rows",
  low_confidence_verifier: "Low-confidence verification",
  admin_override_review: "Admin override follow-ups",
  broken_apply_link: "Broken apply links",
};

/* ── Normalization match methods ─────────────────────────────────────── */
export const MATCH_METHOD_LABELS: Record<string, string> = {
  exact: "Exact match",
  alias: "Known alias",
  token: "Partial text match",
  fuzzy: "Close spelling",
  none: "No match",
};
