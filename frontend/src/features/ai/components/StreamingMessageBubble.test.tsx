/**
 * The reply bubble while an answer is still streaming in (IR-329, IR-596):
 * one status row, then any answer text, with citation markers held back as
 * placeholders. No routing, step or reasoning panel exists to render.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";
import type { StreamingState } from "../conversation/answerStream";

import { StreamingMessageBubble } from "./StreamingMessageBubble";

function state(overrides: Partial<StreamingState> = {}): StreamingState {
  return { activity: "waiting", label: "Waiting…", text: "", citations: [], ...overrides };
}

describe("a still-streaming reply", () => {
  it("shows the status row before any answer text has arrived", () => {
    renderScreen(<StreamingMessageBubble state={state({ activity: "thinking", label: "Thinking…" })} />);

    expect(screen.getByRole("status")).toHaveTextContent("Thinking…");
  });

  it("renders the answer text as it arrives", () => {
    renderScreen(
      <StreamingMessageBubble
        state={state({ activity: "preparing", label: "Preparing your answer…", text: "Rainfall gauges feed the model." })}
      />,
    );

    expect(screen.getByText(/Rainfall gauges feed the model/)).toBeTruthy();
  });

  it("holds a citation marker back as a placeholder rather than raw brackets", () => {
    renderScreen(
      <StreamingMessageBubble
        state={state({ activity: "preparing", label: "Preparing your answer…", text: "Rainfall gauges feed the model [1]." })}
      />,
    );

    expect(screen.queryByText(/\[1\]/)).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("renders no reasoning, routing or step panel, only the one status row", () => {
    renderScreen(
      <StreamingMessageBubble state={state({ activity: "thinking", label: "Thinking…" })} />,
    );

    expect(screen.queryByRole("button", { name: /reasoning/i })).toBeNull();
    for (const prohibited of ["Answer approach", "Why this approach", "Try instead", "search_passages", "find_records"]) {
      expect(screen.queryByText(new RegExp(prohibited, "i"))).toBeNull();
    }
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("puts the status row under the answer text", () => {
    renderScreen(
      <StreamingMessageBubble
        state={state({ activity: "preparing", label: "Preparing your answer…", text: "Two papers use rainfall gauges." })}
      />,
    );

    const answer = screen.getByText(/use rainfall gauges/);
    expect(answer.compareDocumentPosition(screen.getByRole("status")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(
      <StreamingMessageBubble state={state({ activity: "thinking", label: "Thinking…" })} />,
    );

    await expectNoBlockingA11yViolations(container);
  });
});
