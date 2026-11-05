import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";

import { StarterQuestions } from "./StarterQuestions";

describe("starter questions", () => {
  it("offers each question under one group and sends the one chosen", async () => {
    const onChoose = vi.fn();
    const { container } = renderScreen(
      <StarterQuestions questions={["What methods were used?", "What were the findings?"]} onChoose={onChoose} />,
    );

    const group = screen.getByRole("group", { name: "Suggested questions" });
    await userEvent.click(within(group).getByRole("button", { name: "What were the findings?" }));

    expect(onChoose).toHaveBeenCalledExactlyOnceWith("What were the findings?");
    await expectNoBlockingA11yViolations(container);
  });
});
