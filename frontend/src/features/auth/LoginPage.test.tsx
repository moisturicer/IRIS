/**
 * The login screen, asserted through the accessible tree (IR-210).
 *
 * This file is the tracer bullet for the frontend test seam. IR-204 repaired
 * this screen's accessibility by hand and recorded the result in a PR body;
 * that evidence was true when written and stopped being checkable the moment
 * the file was next edited. These tests convert it into a standing assertion.
 *
 * **Every query goes through the accessible tree** -- by role and accessible
 * name, or by label. None by class name, `data-testid`, or component internals.
 * That is not a style rule: the accessible tree is what a screen reader walks,
 * so a test that can still find a control after its label association breaks is
 * a test that cannot detect the bug this suite exists to catch.
 */
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";

import LoginPage from "./LoginPage";

describe("the login screen", () => {
  it("gives every control an accessible name", () => {
    renderScreen(<LoginPage />, { route: "/login" });

    // `getByRole` resolves the name the way an assistive technology would --
    // through the <label for>, not the visible text's position on screen.
    expect(screen.getByRole("textbox", { name: "Email Address" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign In" })).toBeInTheDocument();

    // A password input has no implicit ARIA role, so it is unreachable by role
    // and is queried by its label instead. Still the accessible tree.
    expect(screen.getByLabelText("Password")).toBeInTheDocument();

    // The show/hide toggle's visible text is "Show", but 2.5.3 wants the
    // accessible name to start with it -- hence the aria-label IR-204 added.
    expect(screen.getByRole("button", { name: "Show password" })).toBeInTheDocument();
  });

  it("reaches a validation error as the field's accessible description", async () => {
    const user = userEvent.setup();
    renderScreen(<LoginPage />, { route: "/login" });

    await user.click(screen.getByRole("button", { name: "Sign In" }));

    // The assertion that matters: not "the text appears somewhere on screen",
    // but "the text is announced *for this field*". A message rendered next to
    // an input it is not associated with reads, to a screen reader user, as an
    // unexplained error on a field they cannot identify.
    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: "Email Address" })).toHaveAccessibleDescription(
        "Email is required.",
      );
    });

    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription("Password is required.");
  });

  it("marks the invalid fields as invalid, not merely red", async () => {
    const user = userEvent.setup();
    renderScreen(<LoginPage />, { route: "/login" });

    await user.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: "Email Address" })).toBeInvalid();
    });
    expect(screen.getByLabelText("Password")).toBeInvalid();
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(<LoginPage />, { route: "/login" });

    await expectNoBlockingA11yViolations(container);
  });
});
