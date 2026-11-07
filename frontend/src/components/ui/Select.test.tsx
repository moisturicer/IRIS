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
});
