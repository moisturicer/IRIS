import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { documentsApi } from "@/api/documents";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { ImageReader } from "./ImageReader";
import type { ReaderDocument } from "./readerDocument";

vi.mock("@/api/documents", () => ({
  documentsApi: {
    viewFile: vi.fn(),
    viewUpload: vi.fn(),
  },
}));

const scan: ReaderDocument = { kind: "file", id: 33, label: "Signed consent.png", fileName: "Signed consent.png" };

beforeEach(() => {
  vi.mocked(documentsApi.viewFile).mockResolvedValue({ data: new Blob(["png"], { type: "image/png" }) } as never);
  URL.createObjectURL = vi.fn(() => "blob:scan");
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => vi.clearAllMocks());

describe("an image in Review's reader (IR-1203)", () => {
  it("reads the image through its view route and shows it, named, with zoom and its download", async () => {
    const { container } = render(
      <ImageReader document={scan} fill downloadControl={<button type="button">Download Signed consent.png</button>} />,
    );

    const image = await screen.findByRole("img", { name: "Signed consent.png" });
    expect(image).toHaveAttribute("src", "blob:scan");
    // jsdom loads no image: give it a scan's size and say it loaded, as a browser would.
    Object.defineProperty(image, "naturalWidth", { value: 1200 });
    Object.defineProperty(image, "naturalHeight", { value: 1600 });
    fireEvent.load(image);
    expect(documentsApi.viewFile).toHaveBeenCalledWith(33, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(documentsApi.viewUpload).not.toHaveBeenCalled();

    const tools = screen.getByRole("toolbar", { name: "Image tools" });
    expect(tools).toContainElement(screen.getByRole("button", { name: "Download Signed consent.png" }));
    expect(screen.getByRole("button", { name: "Fit to width" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(screen.getByRole("button", { name: "Fit to width" })).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(screen.getByRole("button", { name: "Fit to width" }));
    expect(screen.getByRole("button", { name: "Fit to width" })).toHaveAttribute("aria-pressed", "true");

    await expectNoBlockingA11yViolations(container);
  });

  it("says when the image could not be read, and tries again", async () => {
    vi.mocked(documentsApi.viewFile).mockRejectedValueOnce(new Error("offline"));
    render(<ImageReader document={scan} fill />);

    expect(await screen.findByText("Could not load Signed consent.png")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("img", { name: "Signed consent.png" })).toBeInTheDocument();
    expect(documentsApi.viewFile).toHaveBeenCalledTimes(2);
  });

  it("lets go of the image's bytes when it is closed", async () => {
    const { unmount } = render(<ImageReader document={scan} fill />);
    await screen.findByRole("img", { name: "Signed consent.png" });

    unmount();
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:scan"));
  });
});
