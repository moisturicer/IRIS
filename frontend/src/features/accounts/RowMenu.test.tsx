/**
 * The "⋯" row menu (IR-1077): a named trigger, a menu of named items, the
 * keyboard a menu owes, and focus back on the trigger after it closes.
 */
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";

import { RowMenu } from "./RowMenu";

function renderMenu(onLock = vi.fn(), onRole = vi.fn()) {
  renderScreen(
    <>
      <button type="button">Before</button>
      <RowMenu
        label="Actions for Stu Dent"
        items={[
          { key: "role", label: "Change role", onSelect: onRole },
          { key: "lock", label: "Lock", danger: true, onSelect: onLock },
        ]}
      />
      <button type="button">Elsewhere</button>
    </>,
  );
  return { onLock, onRole };
}

const trigger = () => screen.getByRole("button", { name: "Actions for Stu Dent" });

describe("the row menu", () => {
  it("is closed until its trigger is pressed, and says so", async () => {
    renderMenu();

    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await userEvent.click(trigger());

    expect(trigger()).toHaveAttribute("aria-expanded", "true");
    const menu = screen.getByRole("menu", { name: "Actions for Stu Dent" });
    expect(within(menu).getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Change role", "Lock"]);
  });

  it("opens onto its first item and moves with the arrow keys, Home and End", async () => {
    renderMenu();
    await userEvent.click(trigger());

    const [role, lock] = screen.getAllByRole("menuitem");
    expect(role).toHaveFocus();
    await userEvent.keyboard("{ArrowDown}");
    expect(lock).toHaveFocus();
    await userEvent.keyboard("{ArrowDown}");
    expect(role).toHaveFocus();
    await userEvent.keyboard("{ArrowUp}");
    expect(lock).toHaveFocus();
    await userEvent.keyboard("{Home}");
    expect(role).toHaveFocus();
    await userEvent.keyboard("{End}");
    expect(lock).toHaveFocus();
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    renderMenu();
    await userEvent.click(trigger());

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger()).toHaveFocus();
  });

  it("closes on a click elsewhere", async () => {
    renderMenu();
    await userEvent.click(trigger());

    await userEvent.click(screen.getByRole("button", { name: "Elsewhere" }));

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("closes on Tab and keeps focus on the trigger", async () => {
    renderMenu();
    await userEvent.click(trigger());

    await userEvent.keyboard("{Tab}");

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger()).toHaveFocus();
  });

  it("runs the chosen item once, closes, and leaves focus on the trigger", async () => {
    const { onLock, onRole } = renderMenu();
    await userEvent.click(trigger());

    await userEvent.click(screen.getByRole("menuitem", { name: "Lock" }));

    expect(onLock).toHaveBeenCalledTimes(1);
    expect(onRole).not.toHaveBeenCalled();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger()).toHaveFocus();
  });

  it("draws no filled button for a destructive item", async () => {
    renderMenu();
    await userEvent.click(trigger());

    const lock = screen.getByRole("menuitem", { name: "Lock" });
    expect(lock.className).not.toMatch(/\bbg-(brand|red|danger)/);
  });

  it("renders nothing at all when there is no item to offer", () => {
    renderScreen(<RowMenu label="Actions for Stu Dent" items={[]} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("has no blocking axe violations open or closed", async () => {
    renderMenu();
    await expectNoBlockingA11yViolations(document.body);
    await userEvent.click(trigger());
    await expectNoBlockingA11yViolations(document.body);
  });
});
