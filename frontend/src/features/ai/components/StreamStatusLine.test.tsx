/**
 * The honest progress copy for an in-flight answer (IR-329) -- one
 * deterministic pipeline stage per line, never agentic phrasing (ADR-028).
 */
import { describe, expect, it } from "vitest";

import { renderScreen, screen } from "@/test/render";
import type { StreamingState } from "../hooks/useAskStream";

import { StreamStatusLine, statusLineText } from "./StreamStatusLine";

function state(overrides: Partial<StreamingState> = {}): StreamingState {
  return { stage: "searching", foundInfo: null, text: "", citations: [], ...overrides };
}

describe("statusLineText", () => {
  it("says IRIS is searching, not that agents are working", () => {
    expect(statusLineText(state({ stage: "searching" }))).toBe("Searching the repository…");
  });

  it("reports the retrieval count once it's known", () => {
    expect(
      statusLineText(state({ stage: "found", foundInfo: { passageCount: 3, recordCount: 2 } })),
    ).toBe("Found 3 passages from 2 papers");
  });

  it("uses the singular for exactly one passage or paper", () => {
    expect(
      statusLineText(state({ stage: "found", foundInfo: { passageCount: 1, recordCount: 1 } })),
    ).toBe("Found 1 passage from 1 paper");
  });

  it("says nothing yet if found fires before the count arrives", () => {
    expect(statusLineText(state({ stage: "found", foundInfo: null }))).toBeNull();
  });

  it("says the model is thinking, not that it is searching", () => {
    expect(statusLineText(state({ stage: "thinking" }))).toBe("Thinking…");
  });

  it("goes silent once the answer itself is rendering", () => {
    expect(statusLineText(state({ stage: "answering" }))).toBeNull();
  });
});

describe("StreamStatusLine", () => {
  it("renders the stage's copy as a live region", () => {
    renderScreen(<StreamStatusLine state={state({ stage: "thinking" })} />);

    expect(screen.getByText("Thinking…")).toBeTruthy();
  });

  it("renders nothing once there is no more status to show", () => {
    const { container } = renderScreen(<StreamStatusLine state={state({ stage: "answering" })} />);

    expect(container.textContent).toBe("");
  });
});
