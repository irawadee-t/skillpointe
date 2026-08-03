"use client";

/**
 * JobPreviewDialog — a quiet "peek at the job description" popup for employer
 * surfaces. Wraps the ONE accessible Dialog primitive (Escape closes, focus
 * is trapped and restored) around the canonical JobSections renderer, so the
 * popup shows the same unified sections as the applicant-facing detail view.
 *
 * `JobPreviewTrigger` is the drop-in affordance: a quiet button (pill or
 * link-like, via `variant`) that opens the dialog without navigating.
 * Mounted at: the employer application detail header, the ranked-applicants
 * page header, and employer jobs list rows.
 */

import { useState } from "react";
import { Eye } from "lucide-react";

import { Dialog } from "@/components/ui/Dialog";
import { cn } from "@/lib/utils";
import { JobSections } from "./JobSections";

export function JobPreviewDialog({
  open,
  onClose,
  jobId,
  jobTitle,
  meta,
  token,
}: {
  open: boolean;
  onClose: () => void;
  jobId: string;
  jobTitle: string;
  /** Quiet context line under the title — employer name, pay, location. */
  meta?: string | null;
  token: string;
}) {
  return (
    <Dialog open={open} onClose={onClose} title={jobTitle} wide>
      <div className="max-h-[70vh] overflow-y-auto pr-1">
        {meta && <p className="mb-4 text-body text-slate">{meta}</p>}
        <JobSections jobId={jobId} token={token} />
      </div>
    </Dialog>
  );
}

export function JobPreviewTrigger({
  jobId,
  jobTitle,
  meta,
  token,
  label = "Preview",
  variant = "pill",
  className,
}: {
  jobId: string;
  jobTitle: string;
  meta?: string | null;
  token: string;
  label?: string;
  /**
   * "pill" = quiet outline pill with icon; "quiet" = icon + text row action
   * (matches the jobs-list row links); "link" = inline link-like text (for
   * eyebrows/headers), no icon.
   */
  variant?: "pill" | "quiet" | "link";
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          variant === "pill" && "btn-pill-outline inline-flex items-center gap-1.5",
          variant === "quiet" &&
            "inline-flex items-center gap-1.5 text-body text-slate transition-colors hover:text-ink",
          variant === "link" &&
            "underline decoration-dotted underline-offset-2 transition-colors hover:text-cohere-ink",
          className,
        )}
      >
        {variant !== "link" && <Eye className="h-3.5 w-3.5" aria-hidden="true" />}
        {label}
      </button>
      {/* Mounted only while open: JobSections fetches lazily, and unmounting
          the Dialog runs its cleanup, which restores focus to the trigger. */}
      {open && (
        <JobPreviewDialog
          open
          onClose={() => setOpen(false)}
          jobId={jobId}
          jobTitle={jobTitle}
          meta={meta}
          token={token}
        />
      )}
    </>
  );
}
