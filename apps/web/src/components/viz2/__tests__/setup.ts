import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());

/** Fixed layout width so scale math is deterministic in jsdom. */
export const TEST_WIDTH = 400;

class ResizeObserverStub {
  private readonly cb: ResizeObserverCallback;
  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
  }
  observe(target: Element) {
    this.cb(
      [
        {
          target,
          contentRect: { width: TEST_WIDTH, height: 0 } as DOMRectReadOnly,
        } as ResizeObserverEntry,
      ],
      this as unknown as ResizeObserver,
    );
  }
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver =
  ResizeObserverStub as unknown as typeof ResizeObserver;

// jsdom doesn't implement scrollTo on elements; components that pin chat
// scroll (useStickToBottom) call it on mount. A no-op keeps tests honest
// about everything except actual pixel scrolling, which jsdom can't do anyway.
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = () => {};
}

Element.prototype.getBoundingClientRect = function () {
  return {
    width: TEST_WIDTH,
    height: 0,
    top: 0,
    left: 0,
    bottom: 0,
    right: TEST_WIDTH,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect;
};
