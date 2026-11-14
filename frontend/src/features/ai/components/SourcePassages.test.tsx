/**
 * What a reader sees under an answer's sources (IR-1090, spec §4.11): the paper's
 * title, the section, the page and a snippet with no Markdown in it, and a link
 * that opens the paper at that page.
 */
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";
import type { Citation, SemanticSearchResult } from "@/types/ai";

import { SourcePassages } from "./SourceContextPanel";

const citation: Citation = {
  marker:       1,
  chunk_id:     11,
  record_id:    7,
  record_title: "Flood Prediction in the Mananga Catchment",
  page:         4,
  text:         "## 3.2 Methods\nWe trained a **convolutional neural network** on [rainfall gauge](https://x.test) data.",
  context_path: ["Flood Prediction in the Mananga Catchment", "Methods"],
  regions:      [],
};

const card = { id: 7, title: "Flood Prediction in the Mananga Catchment", authors: "A. Reyes", year: 2024 } as SemanticSearchResult;

describe("a source under an answer", () => {
  it("shows the paper's title, the section and the page", () => {
    // The snippet does not say "Methods", so the section can only come from the trail.
    renderScreen(
      <SourcePassages citations={[{ ...citation, text: "We trained a network." }]} sources={[card]} answered />,
    );

    const paper = screen.getByRole("region", { name: "Flood Prediction in the Mananga Catchment" });
    const row = within(paper).getByRole("link", { name: /at page 4/i });
    expect(row).toHaveTextContent("Methods");
    expect(row).toHaveTextContent("p. 4");
  });

  it("shows a snippet with no Markdown syntax", () => {
    renderScreen(<SourcePassages citations={[citation]} sources={[card]} answered />);

    const row = screen.getByRole("link", { name: /at page 4/i });
    expect(row).toHaveTextContent("We trained a convolutional neural network on rainfall gauge data.");
    expect(row.textContent).not.toMatch(/[*#[\]]|https?:/);
  });

  it("opens the paper at that page", () => {
    renderScreen(<SourcePassages citations={[citation]} sources={[card]} answered />);

    expect(screen.getByRole("link", { name: /at page 4/i })).toHaveAttribute("href", "/records/7?page=4");
  });

  it("does not repeat the paper's own title as its section", () => {
    renderScreen(
      <SourcePassages
        citations={[{ ...citation, context_path: ["Flood Prediction in the Mananga Catchment"] }]}
        sources={[card]}
        answered
      />,
    );

    const row = screen.getByRole("link", { name: /at page 4/i });
    expect(row).not.toHaveTextContent("Flood Prediction");
  });

  it("names the section the passage sits in, the innermost one", () => {
    renderScreen(
      <SourcePassages
        citations={[{ ...citation, context_path: ["Flood Prediction", "Methods", "## Data collection"] }]}
        sources={[card]}
        answered
      />,
    );

    expect(screen.getByRole("link", { name: /at page 4/i })).toHaveTextContent("Data collection");
  });

  it("still opens a replayed source that kept only its pointer", () => {
    renderScreen(
      <SourcePassages citations={[{ marker: 1, record_id: 7, chunk_id: 11, page: 4 }]} sources={[card]} answered />,
    );

    expect(screen.getByRole("link", { name: /at page 4/i })).toHaveAttribute("href", "/records/7?page=4");
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(<SourcePassages citations={[citation]} sources={[card]} answered />);

    await expectNoBlockingA11yViolations(container);
  });
});
