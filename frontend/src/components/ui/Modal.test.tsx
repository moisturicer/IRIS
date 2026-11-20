import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Modal, type ModalSize } from "./Modal";

/** The dialog panel, for the width and corner it was given. */
function panel() {
  return screen.getByRole("dialog");
}

describe("Modal sizes (IR-1043)", () => {
  it("is the md width and the dialog corner when no size is given", () => {
    render(<Modal open onClose={() => {}} title="Hello">x</Modal>);
    expect(panel()).toHaveClass("max-w-dialog-md", "rounded-dialog");
  });

  it.each<[ModalSize, string]>([
    ["sm", "max-w-dialog-sm"],
    ["md", "max-w-dialog-md"],
    ["lg", "max-w-dialog-lg"],
    ["xl", "max-w-dialog-xl"],
  ])("a %s dialog takes %s", (size, widthClass) => {
    render(<Modal open onClose={() => {}} title="Hello" size={size}>x</Modal>);
    expect(panel()).toHaveClass(widthClass);
  });

  it("starts a sheet's width at md, so it is full width on a phone", () => {
    render(<Modal open onClose={() => {}} title="Hello" size="lg" sheet>x</Modal>);
    expect(panel()).toHaveClass("md:max-w-dialog-lg", "md:rounded-dialog");
    expect(panel()).not.toHaveClass("max-w-dialog-lg");
  });

  it("refuses a width class or an unknown name at type-check time", () => {
    // These lines are checked by `tsc`, not run: an unknown size is an error.
    const typeChecked = () => (
      <>
        {/* @ts-expect-error a width class is not a size */}
        <Modal open onClose={() => {}} size="max-w-md">x</Modal>
        {/* @ts-expect-error nor is a name outside sm, md, lg and xl */}
        <Modal open onClose={() => {}} size="huge">x</Modal>
      </>
    );
    expect(typeof typeChecked).toBe("function");
  });
});

/**
 * A question asked over a form (IR-1256): Publish's "Delete this draft?" opens
 * over the Publish dialog. Only the top dialog hears Escape and Tab.
 */
describe("a dialog over another (IR-1256)", () => {
  afterEach(() => vi.restoreAllMocks());

  function Stacked({ onCloseForm }: { onCloseForm: () => void }) {
    const [asking, setAsking] = useState(false);
    return (
      <>
        <Modal open onClose={onCloseForm} title="Form">
          <button type="button" onClick={() => setAsking(true)}>Ask</button>
        </Modal>
        <Modal open={asking} onClose={() => setAsking(false)} title="Question" size="sm">
          <button type="button">Yes</button>
          <button type="button">No</button>
        </Modal>
      </>
    );
  }

  it("closes only the top dialog on Escape", async () => {
    const onCloseForm = vi.fn();
    const user = userEvent.setup();
    render(<Stacked onCloseForm={onCloseForm} />);

    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(screen.getByRole("dialog", { name: "Question" })).toBeInTheDocument();
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog", { name: "Question" })).not.toBeInTheDocument();
    expect(onCloseForm).not.toHaveBeenCalled();
    // The form hears Escape again once the question is gone.
    await user.keyboard("{Escape}");
    expect(onCloseForm).toHaveBeenCalledTimes(1);
  });

  it("keeps Tab inside the top dialog", async () => {
    // jsdom lays nothing out, so the trap would see no tabbable control and
    // let Tab through. Give the fixture geometry, not a fake trap.
    vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue(
      [new DOMRect(0, 0, 100, 44)] as unknown as DOMRectList,
    );
    const user = userEvent.setup();
    render(<Stacked onCloseForm={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Ask" }));
    const question = screen.getByRole("dialog", { name: "Question" });
    for (let i = 0; i < 6; i++) {
      await user.tab();
      expect(question).toContainElement(document.activeElement as HTMLElement);
    }
  });
});
