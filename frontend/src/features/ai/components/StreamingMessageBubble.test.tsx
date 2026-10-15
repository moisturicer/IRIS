/**
 * The reply bubble while an answer is still streaming in (IR-329): a status
 * line before any text arrives, then the answer text itself, with citation
 * markers held back as placeholders.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";
import type { StreamingState } from "../hooks/useAskStream";

import { StreamingMessageBubble } from "./StreamingMessageBubble";

function state(overrides: Partial<StreamingState> = {}): StreamingState {
  return {
    stage: "searching", foundInfo: null, text: "", reasoning: "", citations: [], ...overrides,
  };
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

  it("offers the reasoning collapsed while the answer is still writing", async () => {
    renderScreen(
      <StreamingMessageBubble
        state={state({
          stage: "answering",
          text: "Rainfall gauges feed the model.",
          reasoning: "The gauges are named in the Methods section.",
        })}
      />,
    );

    expect(screen.queryByText(/named in the Methods section/)).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /reasoning/i }));
    expect(screen.getByRole("region", { name: "Reasoning" }).textContent).toBe(
      "The gauges are named in the Methods section.",
    );
  });

  it("offers no reasoning panel when none arrived", () => {
    renderScreen(<StreamingMessageBubble state={state({ stage: "thinking" })} />);

    expect(screen.queryByRole("button", { name: /reasoning/i })).toBeNull();
  });

  it("says what it is doing in one polite live line, under the answer (IR-570)", () => {
    const { container } = renderScreen(
      <StreamingMessageBubble
        state={state({
          stage: "searching",
          text: "Two of the papers so far use rainfall gauges.",
          candidates: [
            { record_id: 1, title: "Flood Prediction", state: "included" },
            { record_id: 2, title: "Tilapia Ponds", state: "pending" },
          ],
        })}
      />,
    );

    const live = container.querySelectorAll("[aria-live], [role=status], [role=log], [role=alert]");
    expect(live).toHaveLength(1);
    expect(live[0]).toHaveAttribute("aria-live", "polite");
    expect(live[0].textContent).toBe("Screening 2 candidate papers (1 checked)…");

    const answer = screen.getByText(/use rainfall gauges/);
    expect(answer.compareDocumentPosition(live[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps the live line in place while it has nothing to say, so the next stage is announced", () => {
    const { container, rerender } = renderScreen(
      <StreamingMessageBubble state={state({ stage: "found", foundInfo: null })} />,
    );
    const live = container.querySelector("[aria-live]");
    expect(live?.textContent).toBe("");

    rerender(<StreamingMessageBubble state={state({ stage: "thinking" })} />);

    expect(container.querySelector("[aria-live]")).toBe(live);
    expect(live?.textContent).toBe("Thinking…");
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(
      <StreamingMessageBubble state={state({ stage: "thinking" })} />,
    );

    await expectNoBlockingA11yViolations(container);
  });
});
