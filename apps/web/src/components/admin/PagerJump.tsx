"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/**
 * Small "Page N of M, [input]" jump-to-page control.
 * Rendered next to Prev/Next on the admin list pages.
 */
export function PagerJump({
  basePath,
  params,
  page,
  totalPages,
}: {
  basePath: string;
  params: Record<string, string | undefined>;
  page: number;
  totalPages: number;
}) {
  const router = useRouter();
  const [val, setVal] = useState(String(page));

  function go(raw: string) {
    const next = Math.max(1, Math.min(totalPages, Number(raw) || 1));
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v != null && k !== "page") qs.set(k, String(v));
    }
    qs.set("page", String(next));
    router.push(`${basePath}?${qs.toString()}`);
  }

  return (
    <span className="inline-flex items-center gap-1.5 text-caption text-slate">
      <span>
        Page <span className="tabular-nums font-medium text-cohere-ink">{page}</span> of{" "}
        <span className="tabular-nums font-medium text-cohere-ink">{totalPages}</span>
      </span>
      <span aria-hidden className="text-slate-muted">—</span>
      <input
        type="number"
        min={1}
        max={totalPages}
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); go(val); } }}
        onBlur={() => { if (val !== String(page)) go(val); }}
        className="w-14 rounded-md border border-hairline bg-white px-2 py-0.5 text-caption tabular-nums text-cohere-ink focus:border-cohere-ink focus:outline-none"
        aria-label="Jump to page"
      />
    </span>
  );
}
