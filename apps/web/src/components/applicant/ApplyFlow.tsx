"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Check, ExternalLink, Loader2 } from "lucide-react";

import {
  Application, ApplyContext, getApplyContext,
} from "@/lib/api/transactions";
import { ApplySheet } from "@/components/applicant/ApplySheet";
import { useViewAs, VIEW_AS_READONLY_TOOLTIP } from "@/hooks/useViewAs";

/**
 * Apply panel on the match detail page.
 *
 * Indicates which apply path this job has and opens the one-click ApplySheet
 * for internal applications:
 *   - internal enabled  → "Apply on SKILLED Nation" (brand-red commit pill),
 *                         with "Apply on employer site ↗" as a ghost secondary
 *                         when an external link also exists
 *   - external only     → ghost "Apply on employer site ↗"
 *   - already applied   → "Applied · <when>" state, no reload needed
 */
export function ApplyFlow({
  token, jobId, jobTitle, sourceUrl,
}: {
  token: string;
  jobId: string;
  jobTitle?: string;
  sourceUrl?: string | null;
}) {
  const { isViewAs } = useViewAs();
  const [ctx, setCtx] = useState<ApplyContext | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [justApplied, setJustApplied] = useState<Application | null>(null);

  useEffect(() => {
    getApplyContext(token, jobId).then(setCtx).catch(() => setLoadFailed(true));
  }, [token, jobId]);

  const externalUrl = ctx?.external_url ?? sourceUrl ?? null;

  // ----- Applied state (on load, or optimistically after the sheet) ---------
  const applied = justApplied
    ? { id: justApplied.id, status: justApplied.status, when: "Just now" }
    : ctx?.already_applied && ctx.already_applied.status !== "withdrawn"
      ? {
          id: ctx.already_applied.id,
          status: ctx.already_applied.status,
          when: new Date(ctx.already_applied.submitted_at).toLocaleDateString(undefined, {
            month: "short", day: "numeric",
          }),
        }
      : null;

  if (loadFailed && !sourceUrl) return null;

  if (applied) {
    return (
      <section className="rounded-[14px] border border-cohere-green/30 bg-wash-green p-6">
        <div className="flex items-center gap-2">
          <Check className="h-5 w-5 text-cohere-green" strokeWidth={2} />
          <h3 className="text-[1.0625rem] font-medium text-cohere-ink">
            Applied · {applied.when}
          </h3>
        </div>
        <p className="mt-2 text-body text-cohere-ink">
          {justApplied
            ? "The employer will review it and can propose interview times. We'll let you know when they respond."
            : "You've applied to this job on SKILLED Nation."}
        </p>
        {applied.id && (
          <a
            href={`/applicant/applications/${applied.id}`}
            className="btn-primary mt-4 inline-flex items-center gap-1.5"
          >
            See it in your applications <ArrowRight className="h-4 w-4" />
          </a>
        )}
      </section>
    );
  }

  const internal = !!ctx && ctx.job_active && ctx.internal_apply_enabled;
  const withdrawnReapply = ctx?.already_applied?.status === "withdrawn";

  // Nothing to offer: no internal path, no external link.
  if (ctx && !internal && !externalUrl) return null;

  return (
    <section className="rounded-[14px] border border-hairline bg-white p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] font-medium text-studio-maroon">
            {internal ? "Apply on SKILLED Nation" : "Apply for this job"}
          </p>
          <h3 className="mt-1.5 text-[1.0625rem] font-medium text-cohere-ink">
            {jobTitle ? `Apply for ${jobTitle}` : "Send your application"}
          </h3>
          <p className="mt-1.5 max-w-prose text-body text-slate">
            {ctx === null
              ? "Checking how this job takes applications…"
              : internal
                ? withdrawnReapply
                  ? "You withdrew your earlier application. You can re-apply once."
                  : "Apply with your SKILLED profile in two clicks. You'll see exactly what's shared before it sends."
                : "This employer takes applications on their own site."}
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {ctx === null && !loadFailed && (
            <span className="inline-flex items-center gap-2 text-caption text-slate">
              <Loader2 className="h-4 w-4 animate-spin" />
            </span>
          )}
          {internal && (
            <button
              onClick={() => setSheetOpen(true)}
              disabled={isViewAs}
              title={isViewAs ? VIEW_AS_READONLY_TOOLTIP : undefined}
              className="btn-commit inline-flex items-center gap-1.5 transition-transform duration-100 active:scale-[0.97] disabled:opacity-50"
            >
              {withdrawnReapply ? "Re-apply on SKILLED Nation" : "Apply on SKILLED Nation"}
            </button>
          )}
          {externalUrl && (
            <a
              href={externalUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost inline-flex items-center gap-1.5"
            >
              Apply on employer site <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      </div>

      <ApplySheet
        token={token}
        jobId={jobId}
        jobTitle={jobTitle}
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        onApplied={(app) => setJustApplied(app)}
      />
    </section>
  );
}
