"use client";

/**
 * Lightweight tooltip — appears on hover / focus. CSS-only positioning so no
 * portal or ref-forwarding needed.
 */
import { useState } from "react";
import { cn } from "@/lib/utils";

interface TooltipProps {
  label: string;
  children: React.ReactNode;
  className?: string;
}

export function Tooltip({ label, children, className }: TooltipProps) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className={cn("relative inline-block", className)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {children}
      {open && (
        <span
          role="tooltip"
          className="pointer-events-none absolute left-1/2 top-full z-40 mt-2 w-56 -translate-x-1/2 rounded-md border border-hairline bg-white px-3 py-2 text-caption text-cohere-ink shadow-[0_8px_28px_-12px_rgba(12,10,9,0.24)]"
        >
          {label}
        </span>
      )}
    </span>
  );
}
