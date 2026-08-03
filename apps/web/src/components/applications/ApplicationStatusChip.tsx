import {
  APPLICATION_STATUS_TONES,
  statusChipClass,
} from "@/components/ui/statusTones";
import {
  type ApplicationStatus,
  EMPLOYER_STATUS_LABELS,
  STATUS_LABELS,
} from "./stages";

/**
 * The ONE application-status chip. Both the employer and applicant views
 * render this — same colors for the same status everywhere; only the label
 * wording differs per viewer ("New" vs "Submitted").
 */
export function ApplicationStatusChip({
  status,
  viewer = "applicant",
  className,
}: {
  status: ApplicationStatus;
  viewer?: "applicant" | "employer";
  className?: string;
}) {
  const tone = APPLICATION_STATUS_TONES[status] ?? "neutral";
  const labels = viewer === "employer" ? EMPLOYER_STATUS_LABELS : STATUS_LABELS;
  return (
    <span className={statusChipClass(tone, className)}>
      {labels[status] ?? status}
    </span>
  );
}
