import {
  CheckCircle2, Clock, XCircle, Edit3, Send, EyeOff, AlertTriangle, HelpCircle,
} from "lucide-react";

import { STATUS_TONE_CLASSES } from "@/components/ui/statusTones";

/**
 * One chip per batch/row status. Canonical ROW statuses (agreed across the
 * import pipeline): staged / stale / excluded / published (+ rejected).
 * Batch statuses: draft / pending / approved / rejected / published.
 *
 * Tones come from the semantic slot system (statusTones.ts) — solid dark
 * fills with white text, never a light tint with same-hue darker text.
 *
 * An unmapped status renders LOUD (danger tone, raw value) so a new enum
 * value is caught in development instead of silently reading as "Draft".
 */
const MAP: Record<string, { label: string; Icon: typeof Clock; tone: string }> = {
  // Batch statuses
  draft:     { label: "Draft",       Icon: Edit3,        tone: STATUS_TONE_CLASSES.muted },
  pending:   { label: "In review",   Icon: Clock,        tone: STATUS_TONE_CLASSES.progress },
  approved:  { label: "Approved",    Icon: CheckCircle2, tone: STATUS_TONE_CLASSES.positive },
  published: { label: "Live",        Icon: Send,         tone: STATUS_TONE_CLASSES.positive },
  rejected:  { label: "Needs edits", Icon: XCircle,      tone: STATUS_TONE_CLASSES.attention },
  // Row statuses
  staged:    { label: "In review",          Icon: Clock,         tone: STATUS_TONE_CLASSES.progress },
  stale:     { label: "No longer on site",  Icon: AlertTriangle, tone: STATUS_TONE_CLASSES.attention },
  excluded:  { label: "Excluded",           Icon: EyeOff,        tone: STATUS_TONE_CLASSES.muted },
  held:      { label: "Held: link issue",  Icon: AlertTriangle, tone: STATUS_TONE_CLASSES.attention },
};

export function StatusBadge({ status }: { status: string }) {
  const m = MAP[status] ?? {
    // Loud fallback: an unknown status is a bug, not a draft.
    label: `Unknown status: ${status}`,
    Icon: HelpCircle,
    tone: STATUS_TONE_CLASSES.danger,
  };
  const { Icon } = m;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-micro font-medium ${m.tone}`}>
      <Icon className="h-3 w-3" strokeWidth={2} />
      {m.label}
    </span>
  );
}
