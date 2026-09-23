import { describe, expect, it, vi } from "vitest";

import { fireEvent, renderScreen, screen, waitFor } from "@/test/render";

import { CopyButton } from "./CopyButton";

describe("CopyButton", () => {
  it("copies the given text to the clipboard and confirms it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    renderScreen(<CopyButton text="the full answer text" label="Copy answer" />);

    fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));

    expect(writeText).toHaveBeenCalledWith("the full answer text");
    await waitFor(() => expect(screen.getByText("Copied")).toBeTruthy());
  });

  it("does nothing visible when the clipboard is unavailable", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    Object.assign(navigator, { clipboard: { writeText } });

    renderScreen(<CopyButton text="text" label="Copy answer" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));

    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(screen.queryByText("Copied")).toBeNull();
  });
});
