import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { PasswordStrengthMeter } from "./PasswordStrengthMeter";

describe("PasswordStrengthMeter (IR-819)", () => {
  it("says nothing until something is typed", () => {
    const { container } = render(<PasswordStrengthMeter password="" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("says the strength in words, in a polite live region, with no blocking violations", async () => {
    const { container } = render(<PasswordStrengthMeter password="Kalamansi-Tide-42" />);
    const label = screen.getByText("Password strength: Strong");
    expect(label).toHaveAttribute("aria-live", "polite");
    await expectNoBlockingA11yViolations(container);
  });

  it("calls a short password too short", () => {
    render(<PasswordStrengthMeter password="short" />);
    expect(screen.getByText("Password strength: Too short")).toBeInTheDocument();
  });
});
