import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
    const render_ = () => (
      <>
        {/* @ts-expect-error a width class is not a size */}
        <Modal open onClose={() => {}} size="max-w-md">x</Modal>
        {/* @ts-expect-error nor is a name outside sm, md, lg and xl */}
        <Modal open onClose={() => {}} size="huge">x</Modal>
      </>
    );
    expect(typeof render_).toBe("function");
  });
});
