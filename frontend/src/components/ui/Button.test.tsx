/**
 * The danger variant (IR-359). Its colour is maroon like the primary button's,
 * so what makes a destructive action unmistakable is not the colour: it is the
 * verb on the label, which the caller writes, and the warning glyph, which the
 * variant adds on its own.
 */
import { describe, expect, it } from "vitest";
import { Route, Routes } from "react-router-dom";

import { renderScreen, screen, userEvent } from "@/test/render";

import { Button, ButtonLink } from "./Button";

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

/**
 * Every size is 44px on a touch pointer (IR-1092, audit RES-02). `touch:` is the
 * `(pointer: coarse)` media query, not a window width, so a tablet or a phone
 * gets it whatever its size and a mouse never does. jsdom has no layout, so
 * this asserts the class each size asks for; the measured size is the browser
 * check recorded on the PR.
 */
describe("Button touch size (IR-1092)", () => {
  // `full` is already `min-h-11` at every width.
  it.each(["sm", "md", "lg"] as const)("makes %s at least 44px tall on a touch pointer", (size) => {
    renderScreen(
      <>
        <Button size={size}>Button</Button>
        <ButtonLink to="/x" size={size}>Link</ButtonLink>
      </>,
    );

    expect(screen.getByRole("button", { name: "Button" })).toHaveClass("touch:min-h-11");
    expect(screen.getByRole("link", { name: "Link" })).toHaveClass("touch:min-h-11");
  });

  it("keeps the icon button a 44px square on touch even beside a wide window", () => {
    renderScreen(<Button size="icon" aria-label="Open">x</Button>);

    expect(screen.getByRole("button", { name: "Open" })).toHaveClass("touch:w-11", "touch:h-11");
  });
});

/**
 * A navigation action is a link, not a button (IR-538, IR-213's decision), but
 * it looks like one. `ButtonLink` renders an anchor through the same variant
 * and size steps, so no caller copies the button's classes onto an `<a>`.
 */
describe("ButtonLink", () => {
  it("renders a link with the label as its accessible name, and reaches its destination", async () => {
    renderScreen(
      <Routes>
        <Route path="/" element={<ButtonLink to="/login">Sign in</ButtonLink>} />
        <Route path="/login" element={<p>Sign-in screen</p>} />
      </Routes>,
    );

    await userEvent.click(screen.getByRole("link", { name: "Sign in" }));

    expect(screen.getByText("Sign-in screen")).toBeInTheDocument();
  });

  it("takes the same variant and size steps as the button", () => {
    renderScreen(
      <>
        <Button variant="outline" size="full">Same</Button>
        <ButtonLink to="/x" variant="outline" size="full">Same</ButtonLink>
      </>,
    );

    const button = screen.getByRole("button", { name: "Same" });
    const link = screen.getByRole("link", { name: "Same" });
    expect(link).toHaveClass(...button.className.split(/\s+/).filter(Boolean));
  });
});
