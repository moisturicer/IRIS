/**
 * The confirm dialog (IR-359). A destructive confirm is maroon like any other,
 * so it must still ask, name the action on its button, and carry the danger
 * glyph -- and a non-destructive confirm must not.
 */
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";

import { ConfirmDialog } from "./ConfirmDialog";

function open(danger: boolean) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const view = renderScreen(
    <ConfirmDialog
      open
      title="Reject this record permanently?"
      message="The owner cannot resubmit."
      confirmLabel="Reject permanently"
      danger={danger}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />,
  );
  return { ...view, onConfirm, onCancel };
}

describe("ConfirmDialog", () => {
  it("asks before a destructive action and names it on the button", async () => {
    const { container, onConfirm, onCancel } = open(true);

    expect(screen.getByText("Reject this record permanently?")).toBeInTheDocument();
    expect(screen.getByText("The owner cannot resubmit.")).toBeInTheDocument();
    expect(container.querySelector("i.fa-triangle-exclamation")).not.toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Reject permanently" }));
    expect(onConfirm).toHaveBeenCalledOnce();

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("gives a non-destructive confirm no danger glyph", () => {
    const { container } = open(false);

    expect(container.querySelector("i.fa-triangle-exclamation")).toBeNull();
  });

  it("says it is working while confirming, and blocks both buttons", () => {
    const { container } = renderScreen(
      <ConfirmDialog open title="Decline?" message="…" confirmLabel="Decline" danger confirming
        onConfirm={() => {}} onCancel={() => {}} />,
    );

    expect(screen.getByRole("button", { name: "Please wait…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    // The spinner takes the glyph's place, as it does on any loading Button.
    expect(container.querySelector("i.fa-triangle-exclamation")).toBeNull();
  });

  // Built on `Modal` (IR-412, spec §4.13): a dialog named by its title, that
  // Escape cancels, that hands focus back to whatever opened it.
  it("is a dialog named by its title, which Escape cancels", async () => {
    const { onCancel } = open(true);

    expect(screen.getByRole("dialog", { name: "Reject this record permanently?" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("cannot be escaped while it is confirming", async () => {
    const onCancel = vi.fn();
    renderScreen(
      <ConfirmDialog open title="Decline?" message="…" confirmLabel="Decline" confirming
        onConfirm={() => {}} onCancel={onCancel} />,
    );

    await userEvent.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("gives focus back to the control that opened it", async () => {
    function Host() {
      const [shown, setShown] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setShown(true)}>Reject</button>
          <ConfirmDialog open={shown} title="Reject?" message="…" onConfirm={() => {}}
            onCancel={() => setShown(false)} />
        </>
      );
    }
    renderScreen(<Host />);

    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(screen.getByRole("dialog", { name: "Reject?" })).toContainElement(document.activeElement as HTMLElement);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toHaveFocus();
  });

  it("says why the last attempt failed, keeping the choice in front of them", async () => {
    const { container } = renderScreen(
      <ConfirmDialog open title="Publish?" message="It becomes public." error="This record is no longer yours to decide."
        onConfirm={() => {}} onCancel={() => {}} />,
    );

    const dialog = screen.getByRole("dialog", { name: "Publish?" });
    expect(within(dialog).getByRole("alert")).toHaveTextContent("This record is no longer yours to decide.");
    expect(within(dialog).getByRole("button", { name: "Confirm" })).toBeEnabled();
    await expectNoBlockingA11yViolations(container);
  });
});
