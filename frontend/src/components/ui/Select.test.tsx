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

  it("says it is required in words, without putting the word in its name", () => {
    renderScreen(<Colleges required />);

    // The name stays "College"; the requirement is announced as a state.
    const field = screen.getByRole("combobox", { name: "College" });
    expect(field).toBeRequired();
    expect(screen.getByText("(required)")).toBeInTheDocument();
  });
});
