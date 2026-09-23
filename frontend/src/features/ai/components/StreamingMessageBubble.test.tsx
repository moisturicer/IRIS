/**
 * The reply bubble while an answer is still streaming in (IR-329): a status
 * line before any text arrives, then the answer text itself, with citation
 * markers held back as placeholders.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";
import type { StreamingState } from "../hooks/useAskStream";

import { StreamingMessageBubble } from "./StreamingMessageBubble";

function state(overrides: Partial<StreamingState> = {}): StreamingState {
  return { stage: "searching", foundInfo: null, text: "", citations: [], ...overrides };
}

describe("a still-streaming reply", () => {
  it("shows the status line before any answer text has arrived", () => {
    renderScreen(<StreamingMessageBubble state={state({ stage: "searching" })} />);

    expect(screen.getByText("Searching the repository…")).toBeTruthy();
  });

  it("renders the answer text as it arrives", () => {
    renderScreen(
      <StreamingMessageBubble
        state={state({ stage: "answering", text: "Rainfall gauges feed the model." })}
      />,
    );

    expect(screen.getByText(/Rainfall gauges feed the model/)).toBeTruthy();
  });

  it("holds a citation marker back as a placeholder rather than raw brackets", () => {
    renderScreen(
      <StreamingMessageBubble
        state={state({ stage: "answering", text: "Rainfall gauges feed the model [1]." })}
      />,
    );

    expect(screen.queryByText(/\[1\]/)).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(
      <StreamingMessageBubble state={state({ stage: "thinking" })} />,
    );

    await expectNoBlockingA11yViolations(container);
  });
});
