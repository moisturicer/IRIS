import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TONES } from "@/components/ui/statusTones";
import { RequestStatusChip } from "./RequestStatusChip";

/** The chip's icon, if it has one: decorative, so found by its element. */
function iconOf(chip: HTMLElement): string | null {
  return chip.querySelector("i")?.className ?? null;
}

describe("RequestStatusChip (IR-363)", () => {
  it("shows a pending request as quiet grey, with a clock and its word", () => {
    render(<RequestStatusChip state="pending" />);
    const chip = screen.getByText("Pending");
    expect(chip).toHaveClass(...TONES.quiet.split(" "));
    expect(iconOf(chip)).toContain("fa-clock");
  });

  it("shows an approved request as near-black with a check", () => {
    render(<RequestStatusChip state="approved" />);
    const chip = screen.getByText("Approved");
    expect(chip).toHaveClass(...TONES.settled.split(" "));
    expect(iconOf(chip)).toContain("fa-check");
  });

  it("shows declined and revoked requests in maroon, each with its own icon", () => {
    render(<><RequestStatusChip state="declined" /><RequestStatusChip state="revoked" /></>);
    const declined = screen.getByText("Declined");
    const revoked = screen.getByText("Revoked");
    expect(declined).toHaveClass(...TONES.attention.split(" "));
    expect(revoked).toHaveClass(...TONES.attention.split(" "));
    expect(iconOf(declined)).toContain("fa-xmark");
    expect(iconOf(revoked)).toContain("fa-ban");
  });

  it("shows an approval whose access has expired as quiet grey, still named Approved", () => {
    render(<RequestStatusChip state="approved" expired />);
    const chip = screen.getByText("Approved");
    expect(chip).toHaveClass(...TONES.quiet.split(" "));
    expect(iconOf(chip)).toContain("fa-hourglass-end");
  });

  it("shows a cancelled request as quiet grey, with its own icon", () => {
    render(<RequestStatusChip state="cancelled" />);
    const chip = screen.getByText("Cancelled");
    expect(chip).toHaveClass(...TONES.quiet.split(" "));
    expect(iconOf(chip)).toContain("fa-circle-minus");
  });
});
