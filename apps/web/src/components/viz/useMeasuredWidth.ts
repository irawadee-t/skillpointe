"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Measure the rendered width of a container so SVG charts can be laid out in
 * real pixels (crisp hairlines, unscaled text) instead of a stretched viewBox.
 */
export function useMeasuredWidth<T extends HTMLElement = HTMLDivElement>(): [
  React.RefObject<T | null>,
  number,
] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (typeof w === "number") setWidth(w);
    });
    ro.observe(el);
    setWidth(el.getBoundingClientRect().width);
    return () => ro.disconnect();
  }, []);

  return [ref, width];
}
