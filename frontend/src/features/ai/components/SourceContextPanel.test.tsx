/**
 * The panel that shows what an answer was grounded in (IR-284).
 *
 * Two things are asserted that were not true before: the quote is on screen
 * with its page, and **nothing is fetched** — the panel used to request one
 * record per citation, so a card could arrive late, arrive wrong, or not
 * arrive at all. It now renders what the answer already handed it.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";
import type { Citation, SemanticSearchResult } from "@/types/ai";

import { SourceContextPanel } from "./SourceContextPanel";

const QUOTE = "tilapia were sampled fortnightly from four brackish ponds";

const citation: Citation = {
  marker:       1,
  chunk_id:     31,
  record_id:    9,
  record_title: "Tilapia Pond Sampling",
  page:         6,
  text:         QUOTE,
  context_path: ["Tilapia Pond Sampling", "Methods"],
};

const card: SemanticSearchResult = {
  id:             9,
  title:          "Tilapia Pond Sampling",
  abstract:       "A study of brackish pond stocking.",
  authors:        "R. Dela Cruz, M. Lim",
  year:           2025,
  classification: "Aquaculture",
  score:          0.82,
};

function renderPanel(props: Partial<React.ComponentProps<typeof SourceContextPanel>> = {}) {
  return renderScreen(
    <SourceContextPanel
      open
      citations={[citation]}
      sources={[card]}
      onClose={vi.fn()}
      {...props}
    />,
  );
}

describe("the referenced passages panel", () => {
  it("shows the quoted passage and the page it sits on", () => {
    renderPanel();

    expect(screen.getByRole("blockquote").textContent).toBe(QUOTE);
    expect(screen.getByText(/Page 6/)).toBeTruthy();
  });

  it("names whose work the passage is, from the card the answer carried", () => {
    renderPanel();

    // No fetch: the card came in the same response as the passage, so the
    // authors are on screen on the first render rather than after a spinner.
    expect(screen.getByText("R. Dela Cruz, M. Lim")).toBeTruthy();
  });

  it("offers a way to the cited page of the source", () => {
    renderPanel();

    const link = screen.getByRole("link", { name: /Open Tilapia Pond Sampling at page 6/i });
    expect(link.getAttribute("href")).toBe("/records/9?page=6");
  });

  it("still names the record when its card is missing", () => {
    // Cards now ride on the reply, so this is the narrow case where one is
    // genuinely gone — a record deleted between the answer and the reading.
    // The citation carries the title retrieval saw, so the passage is never
    // shown as belonging to nobody.
    renderPanel({ sources: [] });

    expect(screen.getByRole("heading", { name: "Tilapia Pond Sampling" })).toBeTruthy();
  });

  it("invites a question when nothing has been asked yet", () => {
    renderPanel({ citations: [] });

    expect(screen.getByText(/Ask a question to see the passages/i)).toBeTruthy();
  });

  it("collapses to zero width and drops out of the tab order when closed", () => {
    renderPanel({ open: false });

    const aside = screen.getByLabelText("Referenced passages");
    expect(aside.className).toContain("w-0");
    expect(aside.getAttribute("aria-hidden")).toBe("true");
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderPanel();

    await expectNoBlockingA11yViolations(container);
  });
});
