/**
 * The reasoning panel (IR-381).
 *
 * The claim this ticket makes is that a reader can see what the model was
 * working through — live and on a reopened conversation — without that working
 * ever being mistaken for the cited answer. The collapsed-by-default state is
 * the whole mechanism for the second half, so it is what these tests pin.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";

import { ReasoningPanel } from "./ReasoningPanel";

const WORKING = "The gauges are named in the Methods section, so I will cite that.";

describe("the reasoning panel", () => {
  it("starts collapsed, with the reasoning text not on screen", () => {
    renderScreen(<ReasoningPanel reasoning={WORKING} />);

    const toggle = screen.getByRole("button", { name: /reasoning/i });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText(WORKING)).toBeNull();
    expect(screen.queryByRole("region", { name: "Reasoning" })).toBeNull();
  });

  it("reveals the reasoning when the reader expands it", async () => {
    renderScreen(<ReasoningPanel reasoning={WORKING} />);

    await userEvent.click(screen.getByRole("button", { name: /reasoning/i }));

    const region = screen.getByRole("region", { name: "Reasoning" });
    expect(region.textContent).toBe(WORKING);
    expect(screen.getByRole("button", { name: /reasoning/i }).getAttribute("aria-expanded")).toBe(
      "true",
    );
  });

  it("collapses again on a second activation", async () => {
    renderScreen(<ReasoningPanel reasoning={WORKING} />);
    const toggle = screen.getByRole("button", { name: /reasoning/i });

    await userEvent.click(toggle);
    await userEvent.click(toggle);

    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText(WORKING)).toBeNull();
  });

  it("is operable from the keyboard alone", async () => {
    renderScreen(<ReasoningPanel reasoning={WORKING} />);

    await userEvent.tab();
    expect(screen.getByRole("button", { name: /reasoning/i })).toBe(document.activeElement);

    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("region", { name: "Reasoning" }).textContent).toBe(WORKING);
  });

  it("names the panel it controls, so the expanded state is announced", async () => {
    renderScreen(<ReasoningPanel reasoning={WORKING} />);
    const toggle = screen.getByRole("button", { name: /reasoning/i });

    await userEvent.click(toggle);

    expect(screen.getByRole("region", { name: "Reasoning" }).id).toBe(
      toggle.getAttribute("aria-controls"),
    );
  });

  it("renders nothing at all when the model reasoned nothing", () => {
    renderScreen(<ReasoningPanel reasoning="   " />);

    expect(screen.queryByRole("button", { name: /reasoning/i })).toBeNull();
  });

  it("has no serious or critical accessibility violations, collapsed or expanded", async () => {
    const { container } = renderScreen(<ReasoningPanel reasoning={WORKING} />);
    await expectNoBlockingA11yViolations(container);

    await userEvent.click(screen.getByRole("button", { name: /reasoning/i }));
    await expectNoBlockingA11yViolations(container);
  });
});
