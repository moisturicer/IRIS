import { useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { AccountLockedModal } from "./AccountLockedModal";

// jsdom supplies no layout; the shared trap correctly excludes elements with
// no client rect. Supply geometry for this visible fixture, not a fake trap.
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue(
    [new DOMRect(0, 0, 100, 44)] as unknown as DOMRectList,
  );
});
afterEach(() => vi.restoreAllMocks());

function LockDialog() {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  return <>
    <button ref={trigger} disabled={open} onClick={() => setOpen(true)}>Sign in</button>
    <AccountLockedModal open={open} onClose={() => setOpen(false)} lock={{ by: "admin" }} returnTo={trigger.current} />
    <a href="/signup">Register</a>
  </>;
}

describe("the locked-account dialog", () => {
  it("announces the reason, keeps keyboard focus inside, and restores it on Escape", async () => {
    const user = userEvent.setup();
    renderScreen(<LockDialog />);
    const trigger = screen.getByRole("button", { name: "Sign in" });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Account Locked" });
    const close = within(dialog).getByRole("button", { name: "Close" });
    expect(dialog).toHaveAccessibleDescription(/RDCO has locked this account/);
    expect(close).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(close).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("has no blocking accessibility violations", async () => {
    const { container } = renderScreen(<LockDialog />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await expectNoBlockingA11yViolations(container);
  });
});
