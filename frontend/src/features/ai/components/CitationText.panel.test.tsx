/**
 * A citation chip where a Sources panel exists (IR-1237): a numbered button that
 * opens the panel at that passage, not a link away from the conversation. Where
 * no panel is provided (Paper Chat, the AI Overview) it stays the link it was.
 */
import { describe, expect, it, vi } from "vitest";

import { CitationPanelContext } from "@/lib/citedPage";
import { renderScreen, screen, userEvent } from "@/test/render";
import type { Citation } from "@/types/ai";

import { CitationText } from "./CitationText";

const first: Citation = {
  marker: 1, chunk_id: 1, record_id: 1, record_title: "Flood sensors", page: 3,
  text: "river gauges measure water level hourly", context_path: [], regions: [],
};
const second: Citation = {
  marker: 2, chunk_id: 2, record_id: 2, record_title: "Pond sampling", page: 5,
  text: "pond water sampled weekly for turbidity", context_path: [], regions: [],
};
const text = "Both studies sample water: [1] [2].";

describe("a citation chip beside a Sources panel", () => {
  it("is a button named for its source and page, not a link", () => {
    renderScreen(
      <CitationPanelContext.Provider value={{ active: null, open: vi.fn() }}>
        <CitationText text={text} citations={[first, second]} />
      </CitationPanelContext.Provider>,
    );

    expect(screen.getByRole("button", { name: "Source 1: Flood sensors, page 3" })).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: "Source 2: Pond sampling, page 5" })).toHaveTextContent("2");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("opens the panel at its own marker when pressed", async () => {
    const open = vi.fn();
    renderScreen(
      <CitationPanelContext.Provider value={{ active: null, open }}>
        <CitationText text={text} citations={[first, second]} />
      </CitationPanelContext.Provider>,
    );

    await userEvent.click(screen.getByRole("button", { name: /^Source 2:/ }));

    expect(open).toHaveBeenCalledExactlyOnceWith(2);
  });

  it("marks only the open source as pressed", () => {
    renderScreen(
      <CitationPanelContext.Provider value={{ active: 2, open: vi.fn() }}>
        <CitationText text={text} citations={[first, second]} />
      </CitationPanelContext.Provider>,
    );

    expect(screen.getByRole("button", { name: /^Source 2:/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /^Source 1:/ })).toHaveAttribute("aria-pressed", "false");
  });

  it("leaves out the page when the citation has none", () => {
    renderScreen(
      <CitationPanelContext.Provider value={{ active: null, open: vi.fn() }}>
        <CitationText text="Seen [1]." citations={[{ ...first, page: null }]} />
      </CitationPanelContext.Provider>,
    );

    expect(screen.getByRole("button", { name: "Source 1: Flood sensors" })).toBeInTheDocument();
  });

  it("stays a link to the paper with no panel, and for the Overview's page markers", () => {
    renderScreen(<CitationText text={text} citations={[first, second]} />);
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });
});
