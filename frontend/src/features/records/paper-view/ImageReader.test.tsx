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
const form: ReaderDocument = { kind: "file", id: 34, label: "Survey form.jpg", fileName: "Survey form.jpg" };
const bytes = (name: string) => ({ data: new Blob([name], { type: "image/png" }) });

// jsdom has no object URLs: each test gets its own, named after the bytes, and the originals come back after.
const { createObjectURL, revokeObjectURL } = URL;
beforeEach(() => {
  vi.mocked(documentsApi.viewFile).mockResolvedValue(bytes("scan") as never);
  URL.createObjectURL = vi.fn((blob: Blob) => `blob:${(blob as Blob & { size: number }).size}-${Math.random()}`);
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
  URL.createObjectURL = createObjectURL;
  URL.revokeObjectURL = revokeObjectURL;
  vi.clearAllMocks();
});

/** jsdom loads no image: give it a scan's size and say it loaded, as a browser would. */
function loaded(image: HTMLElement) {
  Object.defineProperty(image, "naturalWidth", { value: 1200 });
  Object.defineProperty(image, "naturalHeight", { value: 1600 });
  fireEvent.load(image);
}

describe("an image in Review's reader (IR-1203)", () => {
  it("reads the image through its view route and shows it, named, with zoom and its download", async () => {
    const { container } = render(
      <ImageReader document={scan} downloadControl={<button type="button">Download Signed consent.png</button>} />,
    );

    const image = await screen.findByRole("img", { name: "Signed consent.png" });
    expect(image.getAttribute("src")).toMatch(/^blob:/);
    loaded(image);
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
    render(<ImageReader document={scan} />);

    expect(await screen.findByText("Could not load Signed consent.png")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("img", { name: "Signed consent.png" })).toBeInTheDocument();
    expect(documentsApi.viewFile).toHaveBeenCalledTimes(2);
  });

  // A file stored before IR-1220 checked first bytes may be named .png and be something else.
  it("says so when the bytes arrive but are not an image the browser can draw", async () => {
    render(<ImageReader document={scan} />);

    fireEvent.error(await screen.findByRole("img", { name: "Signed consent.png" }));
    expect(await screen.findByText("Could not load Signed consent.png")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("shows only the image it was switched to, and never makes bytes for a read it no longer needs", async () => {
    let finishFirst: (value: unknown) => void = () => {};
    vi.mocked(documentsApi.viewFile)
      .mockImplementationOnce(() => new Promise((resolve) => { finishFirst = resolve; }) as never)
      .mockResolvedValueOnce(bytes("the survey form") as never);
    const { rerender } = render(<ImageReader document={scan} />);

    rerender(<ImageReader document={form} />);
    expect(await screen.findByRole("img", { name: "Survey form.jpg" })).toBeInTheDocument();
    finishFirst(bytes("scan"));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(screen.queryByRole("img", { name: "Signed consent.png" })).not.toBeInTheDocument();
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  });

  it("starts each image fitted to the width, whatever the last one was zoomed to", async () => {
    const { rerender } = render(<ImageReader document={scan} />);
    loaded(await screen.findByRole("img", { name: "Signed consent.png" }));
    await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(screen.getByRole("button", { name: "Fit to width" })).toHaveAttribute("aria-pressed", "false");

    rerender(<ImageReader document={form} />);
    loaded(await screen.findByRole("img", { name: "Survey form.jpg" }));
    expect(screen.getByRole("button", { name: "Fit to width" })).toHaveAttribute("aria-pressed", "true");
  });

  it("lets go of the image's bytes when it is closed", async () => {
    const { unmount } = render(<ImageReader document={scan} />);
    const src = (await screen.findByRole("img", { name: "Signed consent.png" })).getAttribute("src");

    unmount();
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith(src));
  });
});
