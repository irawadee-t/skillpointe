"use client";

import { useEffect, useState } from "react";

/**
 * Returns `value` after it has been stable for `delayMs`. The universal
 * debounce for live type-ahead search — pair with an effect keyed on the
 * debounced value to fetch/narrow as the user types.
 */
export function useDebouncedValue<T>(value: T, delayMs = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}
