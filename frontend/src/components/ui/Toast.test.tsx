/**
 * Toast kinds (IR-359). Success and error are both dark once the palette is
 * white, black, grey and maroon, so a kind is carried by its glyph and by a
 * word a screen reader hears, never by the tone alone.
 */
import { afterEach, describe, expect, it } from "vitest";

import { useUIStore } from "@/store/ui.store";
import { renderScreen, screen, userEvent } from "@/test/render";

import { ToastContainer } from "./Toast";

afterEach(() => useUIStore.setState({ toasts: [] }));

function show(type: "success" | "error" | "info", message: string) {
  useUIStore.setState({ toasts: [{ id: type, type, message }] });
  return renderScreen(<ToastContainer />);
}

describe("ToastContainer", () => {
  it.each([
    ["success", "Success:", "fa-circle-check"],
    ["error",   "Error:",   "fa-circle-xmark"],
    ["info",    "Notice:",  "fa-circle-info"],
  ] as const)("says what kind a %s toast is in words and with a glyph", (type, word, glyph) => {
    const { container } = show(type, "Record saved");

    // The word is read before the message, so the kind is heard first.
    expect(screen.getByText("Record saved").parentElement).toHaveTextContent(`${word}Record saved`);
    expect(container.querySelector(`i.${glyph}`)).toHaveAttribute("aria-hidden");
  });

  it("still dismisses", async () => {
    show("info", "Record saved");

    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(useUIStore.getState().toasts).toEqual([]);
  });
});
