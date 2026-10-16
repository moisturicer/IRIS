/**
 * The collapsed reasoning summary (IR-596): a disclosure button that owns its
 * body, a body that is absent until opened, and nothing at all when empty.
 */
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";

import { ReasoningSummary } from "./ReasoningSummary";

const SUMMARY = "The two studies share a problem, but their settings differ.";

describe("the reasoning summary", () => {
  it("starts collapsed, with its body absent from the document", () => {
    const { container } = renderScreen(<ReasoningSummary summary={SUMMARY} />);

    const toggle = screen.getByRole("button", { name: "Reasoning summary" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(container.textContent).not.toContain(SUMMARY);
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("opens and closes with Enter and with Space, keeping aria-controls on the body", async () => {
    renderScreen(<ReasoningSummary summary={SUMMARY} />);
    const toggle = screen.getByRole("button", { name: "Reasoning summary" });

    toggle.focus();
    await userEvent.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const body = screen.getByRole("region", { name: "Reasoning summary" });
    expect(body.textContent).toBe(SUMMARY);
    expect(toggle.getAttribute("aria-controls")).toBe(body.id);

    await userEvent.keyboard(" ");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(SUMMARY)).toBeNull();

    await userEvent.keyboard(" ");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it.each([undefined, "", "   "])("renders no control for an empty summary (%j)", (summary) => {
    const { container } = renderScreen(<ReasoningSummary summary={summary} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("has no serious or critical accessibility violations, open or closed", async () => {
    const { container } = renderScreen(<ReasoningSummary summary={SUMMARY} />);
    await expectNoBlockingA11yViolations(container);

    await userEvent.click(screen.getByRole("button", { name: "Reasoning summary" }));
    await expectNoBlockingA11yViolations(container);
  });
});
