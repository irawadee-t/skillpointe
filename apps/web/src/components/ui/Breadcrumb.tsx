import Link from "next/link";
import { ChevronRight } from "lucide-react";

/**
 * Breadcrumb — small path indicator at the top of subpages so a worker/employer
 * always knows where they are and how to get back to the parent surface.
 * Sits *above* the PageHeader; renders as: Parent / Current
 */
export interface Crumb {
  label: string;
  href?: string;      // omit on the last (current) crumb
}

export function Breadcrumb({ items, className = "" }: { items: Crumb[]; className?: string }) {
  return (
    <nav aria-label="Breadcrumb" className={`inline-flex items-center gap-1 text-caption ${className}`}>
      {items.map((c, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={i} className="inline-flex items-center gap-1">
            {c.href && !isLast ? (
              <Link href={c.href} className="text-slate transition-colors hover:text-cohere-ink">
                {c.label}
              </Link>
            ) : (
              <span className={isLast ? "text-cohere-ink" : "text-slate"}>{c.label}</span>
            )}
            {!isLast && <ChevronRight className="h-3 w-3 text-slate-muted" strokeWidth={2} />}
          </span>
        );
      })}
    </nav>
  );
}
