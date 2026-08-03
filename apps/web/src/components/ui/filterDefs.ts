/**
 * Shared, environment-neutral filter definitions (no "use client") — usable
 * from BOTH server pages (empty-state sentences) and the client chip row.
 */

export interface FilterChipDef {
  param: string;
  /** Short facet name shown before the value, e.g. "State". */
  label: string;
  /** Optional value→label prettifier (multi-select options, enum labels). */
  options?: { value: string; label: string }[];
  /** Comma-separated multi-select param — each value gets its own chip. */
  multi?: boolean;
}

/** Human sentence naming the active filters — used by empty states. */
export function describeActiveFilters(
  sp: Record<string, string | undefined>,
  fields: FilterChipDef[],
): string {
  const parts: string[] = [];
  for (const f of fields) {
    const raw = sp[f.param];
    if (!raw) continue;
    const pretty = (v: string) => f.options?.find((o) => o.value === v)?.label ?? v;
    const values = f.multi ? raw.split(",").filter(Boolean).map(pretty) : [pretty(raw)];
    parts.push(`${f.label.toLowerCase()} ${values.join(" or ")}`);
  }
  return parts.join(", ");
}
