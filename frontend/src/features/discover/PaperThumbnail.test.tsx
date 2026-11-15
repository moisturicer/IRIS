import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { recordsApi } from "@/api/records";
import { PaperThumbnail } from "./PaperThumbnail";

vi.mock("@/api/records", () => ({ recordsApi: { manuscriptBlob: vi.fn() } }));

const destroy = vi.fn();
const render_ = vi.fn();
vi.mock("@/lib/pdf", () => ({
  loadPdfDocument: vi.fn(() => Promise.resolve({
    document: { getPage: () => Promise.resolve({}) },
    destroy,
  })),
  renderPageToCanvas: (...args: unknown[]) => {
    render_(...args);
    return { promise: Promise.resolve(), cancel: vi.fn() };
  },
}));

const blob = { data: { arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)) } };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(recordsApi.manuscriptBlob).mockResolvedValue(blob as never);
});

describe("PaperThumbnail", () => {
  it("draws the manuscript's first page over the outline, as decoration", async () => {
    const { container } = render(<PaperThumbnail recordId={5} available />);
    const canvas = container.querySelector("canvas")!;
    await waitFor(() => expect(canvas).toHaveClass("block"));
    expect(recordsApi.manuscriptBlob).toHaveBeenCalledWith(5);
    expect(render_).toHaveBeenCalledTimes(1);
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
    expect(destroy).toHaveBeenCalled();
  });

  it("keeps the outline and fetches nothing when the record has no manuscript", () => {
    const { container } = render(<PaperThumbnail recordId={5} available={false} />);
    expect(container.querySelector("canvas")).toBeNull();
    expect(recordsApi.manuscriptBlob).not.toHaveBeenCalled();
  });

  it("keeps the outline when the manuscript cannot be read", async () => {
    vi.mocked(recordsApi.manuscriptBlob).mockRejectedValue(new Error("down"));
    const { container } = render(<PaperThumbnail recordId={5} available />);
    await waitFor(() => expect(recordsApi.manuscriptBlob).toHaveBeenCalled());
    expect(container.querySelector("canvas")).toHaveClass("hidden");
  });
});
