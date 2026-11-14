/**
 * Toast kinds (IR-359). Success and error are both dark once the palette is
 * white, black, grey and maroon, so a kind is carried by its glyph and by a
 * word a screen reader hears, never by the tone alone.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

  it.each(["success", "error", "info"] as const)(
    "paints a %s toast opaque, because it floats over content (IR-558)",
    (type) => {
      show(type, "Record saved");

      const toast = screen.getByText("Record saved").parentElement!;
      expect(toast.className).not.toMatch(/bg-transparent|bg-white\//);
      // Success is an Ink outline on opaque white since IR-1097 (only Attention is filled).
      expect(toast.className).toMatch(/\bbg-(overlay|surface|brand|stone-900)\b/);
    },
  );

  describe("how long a toast stays", () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it("leaves after a few seconds by default", () => {
      useUIStore.getState().addToast({ type: "info", message: "Saved" });
      expect(useUIStore.getState().toasts).toHaveLength(1);

      vi.advanceTimersByTime(4000);

      expect(useUIStore.getState().toasts).toEqual([]);
    });

    it("stays until dismissed when asked to persist", () => {
      useUIStore.getState().addToast({ type: "error", message: "Not saved", persist: true });

      vi.advanceTimersByTime(60_000);

      expect(useUIStore.getState().toasts).toHaveLength(1);
      useUIStore.getState().removeToast(useUIStore.getState().toasts[0].id);
      expect(useUIStore.getState().toasts).toEqual([]);
    });
  });

  it("still dismisses", async () => {
    show("info", "Record saved");

    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(useUIStore.getState().toasts).toEqual([]);
  });
});
