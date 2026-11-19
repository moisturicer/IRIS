/**
 * The Sources panel (IR-1237): every passage an answer cited, numbered as its
 * chips are, with the chosen one highlighted and scrolled into view.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import type { Citation, SemanticSearchResult } from "@/types/ai";

import { SourcesPanel } from "./SourcesPanel";

const first: Citation = {
  marker: 1, chunk_id: 1, record_id: 1, record_title: "Flood sensors", page: 3,
  text: "river gauges measure water level hourly", context_path: [], regions: [],
};
const second: Citation = {
  marker: 2, chunk_id: 2, record_id: 2, record_title: "Pond sampling", page: 5,
  text: "pond water sampled weekly for turbidity", context_path: [], regions: [],
};
const cards = [
  { id: 1, title: "Flood sensors", authors: "A. Reyes", year: 2024 },
  { id: 2, title: "Pond sampling", authors: "B. Cruz", year: 2022 },
] as SemanticSearchResult[];

function panel(props: Partial<React.ComponentProps<typeof SourcesPanel>> = {}) {
  return renderScreen(
    <SourcesPanel mode="beside" id="sources" citations={[first, second]} sources={cards} active={null}
      question="How do these studies sample water?" onClose={vi.fn()} returnTo={null} {...props} />,
  );
}

beforeEach(() => { Element.prototype.scrollIntoView = vi.fn(); });

describe("the sources an answer cited", () => {
  it("shows each one's number, paper, authors, year, page and quote", () => {
    panel();

    const second = screen.getByRole("listitem", { name: "Source 2: Pond sampling" });
    expect(within(second).getByText("2")).toBeInTheDocument();
    expect(within(second).getByRole("heading", { name: "Pond sampling" })).toBeInTheDocument();
    expect(second).toHaveTextContent("B. Cruz · 2022 · p. 5");
    expect(second).toHaveTextContent("pond water sampled weekly for turbidity");
  });

  it("opens the paper at the cited page", () => {
    panel();

    const link = screen.getByRole("link", { name: "Open at page 5 in Pond sampling" });
    expect(link).toHaveAttribute("href", "/records/2?page=5");
    expect(link).toHaveTextContent("Open at page 5");
  });

  it("highlights the chosen source and brings it into view", () => {
    panel({ active: 2 });

    expect(screen.getByRole("listitem", { name: /^Source 2/ })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("listitem", { name: /^Source 1/ })).not.toHaveAttribute("aria-current");
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("highlights nothing when it was opened from the count", () => {
    panel({ active: null });

    expect(screen.queryByRole("listitem", { current: true })).not.toBeInTheDocument();
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("names the question it describes, and says when nothing was cited", () => {
    panel({ citations: [] });

    expect(screen.getByText(/How do these studies sample water\?/)).toBeInTheDocument();
    expect(screen.getByText("This answer cited no passages.")).toBeInTheDocument();
  });
});

describe("closing the panel", () => {
  it("closes with its X", async () => {
    const onClose = vi.fn();
    panel({ onClose });

    await userEvent.click(screen.getByRole("button", { name: "Close sources" }));

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("closes with Escape", async () => {
    const onClose = vi.fn();
    panel({ onClose });

    await userEvent.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe("over the chat and as a sheet", () => {
  it.each(["over", "sheet"] as const)("is a dialog that Escape closes in %s mode", async (mode) => {
    const onClose = vi.fn();
    panel({ mode, onClose });

    expect(screen.getByRole("dialog", { name: "Sources" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalled();
  });

  it("has no blocking accessibility violations", async () => {
    const { container } = panel({ mode: "sheet", active: 1 });
    await expectNoBlockingA11yViolations(container);
  });
});
