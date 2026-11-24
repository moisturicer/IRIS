/**
 * Select's contract mirrors Input's (IR-539): the label names it, the error or
 * hint is its accessible description, and an error marks it invalid.
 */
import { describe, expect, it } from "vitest";

import { renderScreen, screen } from "@/test/render";

import { Select } from "./Select";

function Colleges(props: Partial<React.ComponentProps<typeof Select>>) {
  return (
    <Select label="College" {...props}>
      <option value="">Select college</option>
      <option value="1">College of Computer Studies</option>
    </Select>
  );
}

describe("Select", () => {
  it("is named by its label", () => {
    renderScreen(<Colleges />);

    expect(screen.getByRole("combobox", { name: "College" })).toBeInTheDocument();
  });

  it("marks an error with a glyph, keeps the message as its description, and announces invalid", () => {
    renderScreen(<Colleges error="Please select your college." />);

    const field = screen.getByRole("combobox", { name: "College" });
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription("Please select your college.");

    const message = screen.getByText("Please select your college.");
    expect(message.querySelector("i.fa-circle-exclamation")).toHaveAttribute("aria-hidden");
  });

  it("describes itself by its hint when there is no error, and is not invalid", () => {
    renderScreen(<Colleges hint="Where your program is offered." />);

    const field = screen.getByRole("combobox", { name: "College" });
    expect(field).toHaveAccessibleDescription("Where your program is offered.");
    expect(field).not.toHaveAttribute("aria-invalid");
  });

  it("drops the hint from its description while an error shows", () => {
    renderScreen(<Colleges hint="Where your program is offered." error="Please select your college." />);

    expect(screen.getByRole("combobox", { name: "College" })).toHaveAccessibleDescription(
      "Please select your college.",
    );
    expect(screen.queryByText("Where your program is offered.")).not.toBeInTheDocument();
  });

  it("announces required as a state and shows nothing, so the name stays the label alone", () => {
    renderScreen(<Colleges required />);

    const field = screen.getByRole("combobox", { name: "College" });
    expect(field).toBeRequired();
    expect(screen.queryByText(/required/i)).not.toBeInTheDocument();
  });

  it("says optional inside the label, so it is part of the name", () => {
    renderScreen(<Colleges optional />);

    const field = screen.getByRole("combobox", { name: "College (optional)" });
    expect(field).not.toBeRequired();
  });

  it("marks nothing when it is neither required nor optional", () => {
    renderScreen(<Colleges />);

    expect(screen.getByRole("combobox", { name: "College" })).not.toBeRequired();
    expect(screen.queryByText(/optional|required/i)).not.toBeInTheDocument();
  });

  it("keeps one slot under the field for its hint or error, so neither moves the form (IR-1303)", () => {
    const { rerender } = renderScreen(<Select label="College" reserveErrorSpace hint="Choose where you study">
        <option value="">Select college</option>
      </Select>);
    const slot = screen.getByText("Choose where you study").parentElement;

    rerender(<Select label="College" reserveErrorSpace hint="Choose where you study" error="Choose a college.">
        <option value="">Select college</option>
      </Select>);
    expect(screen.getByText("Choose a college.").parentElement).toBe(slot);
    expect(screen.getByRole("combobox", { name: "College" })).toHaveAccessibleDescription("Choose a college.");

    // With nothing to say, the slot stays, empty, and describes nothing.
    rerender(<Select label="College" reserveErrorSpace>
        <option value="">Select college</option>
      </Select>);
    expect(slot).toBeInTheDocument();
    expect(slot).toBeEmptyDOMElement();
    expect(screen.getByRole("combobox", { name: "College" })).not.toHaveAttribute("aria-describedby");
  });

  // IR-1313: inline, the control takes the rest of the row, so a caller sizing
  // the row sizes the box, whatever its options are.
  it("fills the rest of its row when inline, and only then", () => {
    const { rerender } = renderScreen(<Colleges inline size="sm" />);
    expect(screen.getByRole("combobox", { name: "College" }).parentElement).toHaveClass("flex-1", "min-w-0");

    rerender(<Colleges />);
    expect(screen.getByRole("combobox", { name: "College" }).parentElement).not.toHaveClass("flex-1");
  });
});
