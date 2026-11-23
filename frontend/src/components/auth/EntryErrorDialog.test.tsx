/**
 * The entry screens' error dialog (IR-1303): a failed sign-in or registration
 * is said in front of the form, so the form itself never moves.
 */
import { useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { EntryErrorDialog, type EntryError } from "./EntryErrorDialog";

// jsdom supplies no layout; the shared trap excludes elements with no client
// rect. Supply geometry for this visible fixture, as AccountLockedModal's does.
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue(
    [new DOMRect(0, 0, 100, 44)] as unknown as DOMRectList,
  );
});
afterEach(() => vi.restoreAllMocks());

const FAILURE: EntryError = {
  title: "Invalid email or password",
  body: "Please check your credentials and try again.",
};

function Failing() {
  const [error, setError] = useState<EntryError | null>(null);
  const password = useRef<HTMLInputElement>(null);
  return <>
    <label htmlFor="pw">Password</label>
    <input id="pw" ref={password} />
    <button type="button" onClick={() => setError(FAILURE)}>Sign in</button>
    <EntryErrorDialog error={error} onClose={() => setError(null)} returnTo={password.current} />
  </>;
}

describe("the entry error dialog", () => {
  it("interrupts as an alert, named by its title and described by its message", async () => {
    renderScreen(<Failing />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const dialog = screen.getByRole("alertdialog", { name: "Invalid email or password" });
    expect(dialog).toHaveAccessibleDescription("Please check your credentials and try again.");
    expect(within(dialog).getByRole("button", { name: "Close" })).toHaveFocus();
  });

  it("closes on Close and returns focus where the page asked", async () => {
    const user = userEvent.setup();
    renderScreen(<Failing />);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await user.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveFocus();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    renderScreen(<Failing />);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveFocus();
  });

  it("has no blocking accessibility violations", async () => {
    const { container } = renderScreen(<Failing />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await expectNoBlockingA11yViolations(container);
  });
});
