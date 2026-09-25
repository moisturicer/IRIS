/**
 * The confirm dialog (IR-359). A destructive confirm is maroon like any other,
 * so it must still ask, name the action on its button, and carry the danger
 * glyph -- and a non-destructive confirm must not.
 */
import { describe, expect, it, vi } from "vitest";

import { renderScreen, screen, userEvent } from "@/test/render";

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
});
