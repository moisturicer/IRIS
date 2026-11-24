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

  it("announces required as a state and shows nothing (IR-585)", () => {
    renderScreen(<Input label="Email" required />);

    const field = screen.getByRole("textbox", { name: "Email" });
    expect(field).toBeRequired();
    expect(screen.queryByText(/required/i)).not.toBeInTheDocument();
  });

  it("says optional inside the label, so it is part of the name (IR-585)", () => {
    renderScreen(<Input label="Middle initial" optional />);

    const field = screen.getByRole("textbox", { name: "Middle initial (optional)" });
    expect(field).not.toBeRequired();
  });

  it("keeps one slot under the field for its hint or error, so neither moves the form (IR-1303)", () => {
    const { rerender } = renderScreen(<Input label="Password" reserveErrorSpace hint="At least 12 characters" />);
    const slot = screen.getByText("At least 12 characters").parentElement;

    rerender(<Input label="Password" reserveErrorSpace hint="At least 12 characters" error="Password is required." />);
    expect(screen.getByText("Password is required.").parentElement).toBe(slot);
    expect(screen.getByRole("textbox", { name: "Password" })).toHaveAccessibleDescription("Password is required.");

    // With nothing to say, the slot stays, empty, and describes nothing.
    rerender(<Input label="Password" reserveErrorSpace />);
    expect(slot).toBeInTheDocument();
    expect(slot).toBeEmptyDOMElement();
    expect(screen.getByRole("textbox", { name: "Password" })).not.toHaveAttribute("aria-describedby");
  });
});
