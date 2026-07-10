import Link from "next/link";
import { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Consistent empty-state block across the app.
 *
 * Style: dashed hairline container, cream ground, one-line headline, optional
 * body, optional primary action. Always suggests a next step — never a bare
 * "No results" wall.
 *
 *   <EmptyState
 *     title="No matches yet"
 *     body="Finish the rest of your profile and matches usually appear within 24h."
 *     action={{ label: "Complete profile", href: "/applicant/profile" }}
 *   />
 */
export function EmptyState({
  icon,
  title,
  body,
  action,
  secondary,
  className,
  size = "md",
}: {
  icon?: ReactNode;
  title: string;
  body?: ReactNode;
  action?: { label: string; href?: string; onClick?: () => void };
  secondary?: { label: string; href?: string; onClick?: () => void };
  className?: string;
  size?: "sm" | "md" | "lg";
}) {
  const padding = size === "sm" ? "px-4 py-6" : size === "lg" ? "px-8 py-14" : "px-6 py-10";
  return (
    <div className={cn(
      "rounded-xl border border-dashed border-hairline bg-parchment/30 text-center",
      padding,
      className,
    )}>
      {icon && <div className="mx-auto mb-3 flex h-8 w-8 items-center justify-center text-slate-muted">{icon}</div>}
      <p className="text-body font-medium text-cohere-ink">{title}</p>
      {body && (
        <p className="mx-auto mt-2 max-w-prose text-[13px] text-slate">{body}</p>
      )}
      {(action || secondary) && (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
          {action && (
            action.href ? (
              <Link href={action.href} className="btn-primary-sm">{action.label}</Link>
            ) : (
              <button onClick={action.onClick} className="btn-primary-sm">{action.label}</button>
            )
          )}
          {secondary && (
            secondary.href ? (
              <Link href={secondary.href} className="text-[13px] text-slate underline decoration-hairline underline-offset-4 hover:text-cohere-ink hover:decoration-cohere-ink">{secondary.label}</Link>
            ) : (
              <button onClick={secondary.onClick} className="text-[13px] text-slate underline decoration-hairline underline-offset-4 hover:text-cohere-ink hover:decoration-cohere-ink">{secondary.label}</button>
            )
          )}
        </div>
      )}
    </div>
  );
}
