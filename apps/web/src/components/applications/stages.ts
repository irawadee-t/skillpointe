/**
 * stages.ts — the ONE canonical application-stage model.
 *
 * Backend enum (application_status_enum, apps/api):
 *   submitted → reviewed → shortlisted → interviewing → offered → hired
 *   plus the terminal states: rejected, withdrawn
 *
 * Both the applications list and the application detail page render their
 * timelines from APPLICATION_STAGES — same names, same count, same order.
 * Sentence case everywhere.
 */

export type ApplicationStatus =
  | "submitted"
  | "reviewed"
  | "shortlisted"
  | "interviewing"
  | "offered"
  | "hired"
  | "rejected"
  | "withdrawn";

export interface ApplicationStage {
  key: Exclude<ApplicationStatus, "rejected" | "withdrawn">;
  label: string;
}

/** Ordered display stages for the progress timeline. */
export const APPLICATION_STAGES: readonly ApplicationStage[] = [
  { key: "submitted", label: "Submitted" },
  { key: "reviewed", label: "Reviewed" },
  { key: "shortlisted", label: "Shortlisted" },
  { key: "interviewing", label: "Interviewing" },
  { key: "offered", label: "Offered" },
  { key: "hired", label: "Hired" },
] as const;

/** Statuses that end the process without a hire — rendered muted, not as a stage. */
export const CLOSED_STATUSES: readonly ApplicationStatus[] = ["rejected", "withdrawn"];

export function isClosedStatus(status: ApplicationStatus): boolean {
  return CLOSED_STATUSES.includes(status);
}

/**
 * Index of the current stage in APPLICATION_STAGES for a given status.
 * Closed statuses return -1 (no active stage on the timeline).
 * `employerViewedAt` bumps a still-"submitted" application to Reviewed —
 * the detail view knows the employer opened the file before the status flips.
 */
export function currentStageIndex(
  status: ApplicationStatus,
  employerViewedAt?: string | null,
): number {
  if (isClosedStatus(status)) return -1;
  const ix = APPLICATION_STAGES.findIndex((s) => s.key === status);
  if (ix <= 0 && employerViewedAt) return Math.max(ix, 1);
  return ix;
}

/** Status → pill label (sentence case). Timeline labels live in APPLICATION_STAGES. */
export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  submitted: "Submitted",
  reviewed: "Reviewed",
  shortlisted: "Shortlisted",
  interviewing: "Interviewing",
  offered: "Offered",
  hired: "Hired",
  rejected: "Closed",
  withdrawn: "Withdrawn",
};

/**
 * Employer-inbox labels for the same statuses ("New" instead of "Submitted",
 * "In review" instead of "Reviewed"). Labels may differ per viewer; COLORS
 * never do — both views take tones from APPLICATION_STATUS_TONES
 * (components/ui/statusTones.ts).
 */
export const EMPLOYER_STATUS_LABELS: Record<ApplicationStatus, string> = {
  submitted: "New",
  reviewed: "In review",
  shortlisted: "Shortlisted",
  interviewing: "Interviewing",
  offered: "Offered",
  hired: "Hired",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};
