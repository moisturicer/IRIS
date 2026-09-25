/**
 * Painting find's matches onto a text layer's spans (IR-353). The spans
 * stand in for the ones pdf.js's `TextLayer` draws: one per text run.
 */
import { describe, expect, it } from "vitest";

import { paintFindHits } from "./findHighlights";

function spansFor(...texts: string[]): HTMLElement[] {
  return texts.map((text) => {
    const span = document.createElement("span");
    span.textContent = text;
    return span;
  });
}

function marked(span: HTMLElement) {
  return Array.from(span.querySelectorAll("mark")).map((mark) => ({
    text: mark.textContent,
    current: mark.classList.contains("find-hit-current"),
  }));
}

describe("paintFindHits", () => {
  it("wraps each match in a mark, and leaves the span's text as it was", () => {
    const spans = spansFor("Robot policies for robots.");

    paintFindHits(spans, [
      { pieces: [{ run: 0, start: 0, end: 5 }], current: true },
      { pieces: [{ run: 0, start: 19, end: 24 }], current: false },
    ]);

    expect(marked(spans[0])).toEqual([
      { text: "Robot", current: true },
      { text: "robot", current: false },
    ]);
    // pdf.js measures a span's text to scale it; it must read the same.
    expect(spans[0].textContent).toBe("Robot policies for robots.");
  });

  it("marks a match that crosses runs in each of them", () => {
    const spans = spansFor("vision ", "language");

    paintFindHits(spans, [
      { pieces: [{ run: 0, start: 0, end: 7 }, { run: 1, start: 0, end: 8 }], current: false },
    ]);

    expect(marked(spans[0])).toEqual([{ text: "vision ", current: false }]);
    expect(marked(spans[1])).toEqual([{ text: "language", current: false }]);
  });

  it("clears the previous find before painting the next, and clears entirely for none", () => {
    const spans = spansFor("robot", "arm");
    paintFindHits(spans, [{ pieces: [{ run: 0, start: 0, end: 5 }], current: true }]);

    paintFindHits(spans, [{ pieces: [{ run: 1, start: 0, end: 3 }], current: true }]);
    expect(marked(spans[0])).toEqual([]);
    expect(marked(spans[1])).toEqual([{ text: "arm", current: true }]);

    paintFindHits(spans, []);
    expect(spans.flatMap(marked)).toEqual([]);
    expect(spans.map((span) => span.textContent)).toEqual(["robot", "arm"]);
  });
});
