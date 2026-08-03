/**
 * AnalyticsChat interaction tests.
 *
 * Pins the two behaviors that read as breakage when they regress:
 *   1. Re-entry guard — a rapid double-click on a suggestion chip fires
 *      EXACTLY one request (the ref guard flips synchronously; `busy` state
 *      alone races because the second click reads a stale closure).
 *   2. Chip persistence — suggested questions never vanish as the
 *      conversation grows; already-asked ones render visually quieted.
 * Plus the streaming presentation: thinking status until the first chunk,
 * progressive text after.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

// jsdom has no canvas — return null so OrbMark/ThinkingOrb take their
// guarded no-context path quietly instead of logging "Not implemented".
beforeAll(() => {
  Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
    value: () => null,
  });
});

vi.mock("@/lib/api/client", () => ({
  apiFetch: vi.fn(),
  API_BASE: "http://api.test",
}));

vi.mock("@/lib/api/sse", () => ({
  postSse: vi.fn(),
  StreamStartError: class StreamStartError extends Error {},
}));

import { AnalyticsChat } from "../AnalyticsChat";
import { apiFetch } from "@/lib/api/client";
import { postSse, type SseEvent } from "@/lib/api/sse";

const apiFetchMock = vi.mocked(apiFetch);
const postSseMock = vi.mocked(postSse);

const EXAMPLES = [
  "Which of my jobs is filling the fastest?",
  "How does my median wage compare to the platform?",
  "What percentage of applicants am I hiring?",
];

/** postSse mock that delivers a full chunked answer immediately. */
function streamImmediately(answer = "Answer.") {
  postSseMock.mockImplementation(async (_url, _init, onEvent) => {
    onEvent({ event: "chunk", data: { delta: answer } });
    onEvent({ event: "done", data: { answer, stubbed: true } });
  });
}

/** postSse mock held open until the test releases it. */
function streamDeferred(answer = "Answer.") {
  let release!: () => void;
  let emit!: (ev: SseEvent) => void;
  postSseMock.mockImplementation(
    (_url, _init, onEvent) =>
      new Promise<void>((resolve) => {
        emit = onEvent;
        release = () => {
          onEvent({ event: "done", data: { answer, stubbed: true } });
          resolve();
        };
      }),
  );
  return {
    emitChunk: (delta: string) => act(() => emit({ event: "chunk", data: { delta } })),
    release: () => act(() => release()),
  };
}

async function renderWithExamples() {
  apiFetchMock.mockResolvedValue(EXAMPLES);
  render(<AnalyticsChat token="tok" />);
  await screen.findByRole("button", { name: EXAMPLES[0] });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("chip re-entry guard", () => {
  it("a rapid double-click fires exactly one request and one turn", async () => {
    await renderWithExamples();
    const stream = streamDeferred("One turn only.");

    const chip = screen.getByRole("button", { name: EXAMPLES[0] });
    // Two clicks in the same frame — before React can flush `busy` state.
    fireEvent.click(chip);
    fireEvent.click(chip);

    expect(postSseMock).toHaveBeenCalledTimes(1);

    stream.release();
    await waitFor(() =>
      expect(screen.getByText("One turn only.")).toBeInTheDocument(),
    );
    // Exactly one question bubble was appended.
    expect(screen.getAllByText(EXAMPLES[0]).length).toBe(2); // chip + one bubble
  });

  it("chips are marked disabled (aria + visual) while an answer is in flight", async () => {
    await renderWithExamples();
    const stream = streamDeferred();

    fireEvent.click(screen.getByRole("button", { name: EXAMPLES[0] }));

    for (const q of EXAMPLES) {
      const chip = screen.getByRole("button", { name: q });
      expect(chip).toHaveAttribute("aria-disabled", "true");
      expect(chip.className).toContain("opacity-40");
    }
    // Clicking a different chip while busy is a no-op too.
    fireEvent.click(screen.getByRole("button", { name: EXAMPLES[1] }));
    expect(postSseMock).toHaveBeenCalledTimes(1);

    stream.release();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: EXAMPLES[0] })).toHaveAttribute(
        "aria-disabled",
        "false",
      ),
    );
  });
});

describe("chip persistence", () => {
  it("chips stay available after several turns, with asked ones quieted", async () => {
    await renderWithExamples();
    streamImmediately("Grounded answer.");

    for (const q of [EXAMPLES[0], EXAMPLES[1]]) {
      fireEvent.click(screen.getByRole("button", { name: q }));
      await waitFor(() =>
        expect(screen.getByRole("button", { name: q })).toHaveAttribute(
          "aria-disabled",
          "false",
        ),
      );
    }

    // 2+ turns in — every suggestion chip is still offered.
    for (const q of EXAMPLES) {
      expect(screen.getByRole("button", { name: q })).toBeInTheDocument();
    }
    // Asked chips are quieted; the unasked one keeps full ink.
    expect(screen.getByRole("button", { name: EXAMPLES[0] }).className).toContain(
      "text-slate-muted",
    );
    expect(screen.getByRole("button", { name: EXAMPLES[2] }).className).toContain(
      "text-ink",
    );
  });
});

describe("streaming presentation", () => {
  it("shows the thinking status until the first chunk, then progressive text", async () => {
    await renderWithExamples();
    const stream = streamDeferred("Full answer text.");

    fireEvent.click(screen.getByRole("button", { name: EXAMPLES[0] }));
    expect(screen.getByRole("status")).toHaveTextContent("Reading your numbers…");

    stream.emitChunk("Full answer ");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText("Full answer")).toBeInTheDocument();

    stream.release();
    await waitFor(() =>
      expect(screen.getByText("Full answer text.")).toBeInTheDocument(),
    );
  });
});
