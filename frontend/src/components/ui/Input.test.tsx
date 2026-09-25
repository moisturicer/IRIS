/**
 * Input's error state (IR-359). Maroon is also the focus colour, so an invalid
 * field is told apart by more than its border: the message carries a glyph and
 * the field announces itself invalid.
 */
import { describe, expect, it } from "vitest";

import { renderScreen, screen } from "@/test/render";

import { Input } from "./Input";

describe("Input", () => {
  it("marks an error with a glyph, keeps the message as its description, and announces invalid", () => {
    renderScreen(<Input label="Email" error="Enter a CIT-U email address." />);

    const field = screen.getByLabelText("Email");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription("Enter a CIT-U email address.");

    const message = screen.getByText("Enter a CIT-U email address.");
    expect(message.querySelector("i.fa-circle-exclamation")).toHaveAttribute("aria-hidden");
  });

  it("shows a hint, with no glyph, when there is no error", () => {
    renderScreen(<Input label="Email" hint="Use your school address." />);

    expect(screen.getByText("Use your school address.").querySelector("i")).toBeNull();
  });
});
