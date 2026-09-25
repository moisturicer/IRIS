/**
 * The danger variant (IR-359). Its colour is maroon like the primary button's,
 * so what makes a destructive action unmistakable is not the colour: it is the
 * verb on the label, which the caller writes, and the warning glyph, which the
 * variant adds on its own.
 */
import { describe, expect, it } from "vitest";

import { renderScreen, screen } from "@/test/render";

import { Button } from "./Button";

describe("Button", () => {
  it("marks a danger action with a glyph, without changing its accessible name", () => {
    const { container } = renderScreen(<Button variant="danger">Decline</Button>);

    expect(screen.getByRole("button", { name: "Decline" })).toBeInTheDocument();
    expect(container.querySelector("i.fa-triangle-exclamation")).toHaveAttribute("aria-hidden");
  });

  it("adds no glyph to a primary action", () => {
    const { container } = renderScreen(<Button>Approve</Button>);

    expect(container.querySelector("i.fa-triangle-exclamation")).toBeNull();
  });

  it("shows the spinner in place of the glyph while a danger action is loading", () => {
    const { container } = renderScreen(<Button variant="danger" loading>Decline</Button>);

    expect(container.querySelector("i.fa-triangle-exclamation")).toBeNull();
    expect(container.querySelector("svg.animate-spin")).not.toBeNull();
  });
});
