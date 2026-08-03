/**
 * SearchWithSuggestions — the shared as-you-type dropdown.
 *
 * Proves the Google-style contract:
 *   1. Typing opens a dropdown that NARROWS per keystroke (g → ge).
 *   2. Prefix matches rank above substring matches.
 *   3. ↑ ↓ Enter pick a suggestion; Enter with no highlight submits the
 *      typed text; Esc closes.
 *   4. Empty state names the query; matched substring is highlighted.
 */
import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SearchWithSuggestions } from "../SearchSuggest";
import type { SuggestionItem } from "@/lib/suggest";

const CATALOG: SuggestionItem[] = [
  { kind: "employer", label: "GE Vernova" },
  { kind: "employer", label: "General Mills" },
  { kind: "employer", label: "Grainger" },
  { kind: "job", label: "Rigger" },        // substring "g", not prefix
];

function fakeFetcher(q: string): Promise<SuggestionItem[]> {
  const needle = q.toLowerCase();
  const matches = CATALOG.filter((c) => c.label.toLowerCase().includes(needle));
  matches.sort(
    (a, b) =>
      Number(!a.label.toLowerCase().startsWith(needle)) -
        Number(!b.label.toLowerCase().startsWith(needle)) ||
      a.label.localeCompare(b.label),
  );
  return Promise.resolve(matches);
}

function Harness({
  onPick,
  onEnter,
  ready = true,
}: {
  onPick?: (i: SuggestionItem) => void;
  onEnter?: () => void;
  ready?: boolean;
}) {
  const [value, setValue] = useState("");
  return (
    <SearchWithSuggestions
      value={value}
      onChange={setValue}
      onPick={(i) => {
        setValue(i.label);
        onPick?.(i);
      }}
      onEnter={onEnter}
      fetchSuggestions={fakeFetcher}
      placeholder="Search…"
      debounceMs={0}
      ready={ready}
    />
  );
}

const optionLabels = () =>
  screen.getAllByRole("option").map((o) => o.textContent);

async function type(input: HTMLElement, text: string) {
  fireEvent.change(input, { target: { value: text } });
  await waitFor(() => expect(screen.getAllByRole("option").length).toBeGreaterThan(0));
}

describe("SearchWithSuggestions", () => {
  it("opens on first character and narrows per keystroke, prefix first", async () => {
    render(<Harness />);
    const input = screen.getByRole("combobox");

    await type(input, "g");
    // All four match "g"; prefix matches (GE, General, Grainger) rank above
    // the substring-only match (Rigger).
    expect(optionLabels()).toEqual([
      "GE Vernova",
      "General Mills",
      "Grainger",
      "Rigger",
    ]);

    // "ge" still matches all four as a substring (grainGEr, rigGEr) but the
    // prefix pair now leads; "gen" narrows to the single true match.
    await type(input, "ge");
    await waitFor(() =>
      expect(optionLabels()).toEqual([
        "GE Vernova",
        "General Mills",
        "Grainger",
        "Rigger",
      ]),
    );

    await type(input, "gen");
    await waitFor(() => expect(optionLabels()).toEqual(["General Mills"]));
  });

  it("bolds the matched substring", async () => {
    render(<Harness />);
    await type(screen.getByRole("combobox"), "ver");
    const option = screen.getByRole("option");
    expect(option.textContent).toBe("GE Vernova");
    const bold = option.querySelector(".font-semibold");
    expect(bold?.textContent).toBe("Ver");
  });

  it("keyboard: ArrowDown + Enter picks; aria-activedescendant roves", async () => {
    const onPick = vi.fn();
    render(<Harness onPick={onPick} />);
    const input = screen.getByRole("combobox");
    await type(input, "ge");

    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input.getAttribute("aria-activedescendant")).toBeTruthy();
    const activeId = input.getAttribute("aria-activedescendant")!;
    expect(document.getElementById(activeId)?.getAttribute("aria-selected")).toBe("true");

    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith(
      expect.objectContaining({ label: "General Mills" }),
    );
    // Picking closes the dropdown.
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
  });

  it("stays closed after a pick until the user types again", async () => {
    // Regression: applying the filter re-renders the page and can hand focus
    // back to the input; the dropdown must not re-open over the results the
    // user just chose.
    render(<Harness />);
    const input = screen.getByRole("combobox");
    await type(input, "ge");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());

    // A refocus must NOT bring it back.
    fireEvent.focus(input);
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByRole("listbox")).toBeNull();

    // Typing again resumes suggestions.
    fireEvent.change(input, { target: { value: "gen" } });
    await waitFor(() => expect(screen.getAllByRole("option").length).toBeGreaterThan(0));
  });

  it("Enter with no highlighted suggestion submits the typed text", async () => {
    const onEnter = vi.fn();
    const onPick = vi.fn();
    render(<Harness onPick={onPick} onEnter={onEnter} />);
    const input = screen.getByRole("combobox");
    await type(input, "ge");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onEnter).toHaveBeenCalledTimes(1);
    expect(onPick).not.toHaveBeenCalled();
  });

  it("Escape closes the dropdown", async () => {
    render(<Harness />);
    const input = screen.getByRole("combobox");
    await type(input, "g");
    fireEvent.keyDown(input, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
  });

  it("never claims 'no matches' while the source is not ready", async () => {
    // Regression: with the session token still resolving, the fetcher returns
    // nothing — that is NOT an honest empty result, so the dropdown must show
    // the loading shimmer rather than "No matches for …".
    const { rerender } = render(<Harness ready={false} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "ge" } });
    // Give the debounce + any resolution a chance to settle.
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByText(/No matches for/)).toBeNull();
    expect(screen.queryAllByRole("option")).toHaveLength(0);

    // Once ready, the same query resolves for real.
    rerender(<Harness ready={true} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "ge" } });
    await waitFor(() => expect(screen.getAllByRole("option").length).toBeGreaterThan(0));
  });

  it("shows an honest empty row naming the query", async () => {
    render(<Harness />);
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "gx" } });
    await waitFor(() =>
      expect(screen.getByText(/No matches for/)).toHaveTextContent("No matches for “gx”"),
    );
  });
});
