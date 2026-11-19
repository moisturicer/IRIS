import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { recordsApi } from "@/api/records";
import { forgetFirstPages } from "@/lib/firstPages";
import { useAuthStore } from "@/store/auth.store";
import { PaperThumbnail } from "./PaperThumbnail";

vi.mock("@/api/records", () => ({ recordsApi: { firstPage: vi.fn() } }));

const createObjectURL = vi.fn((_: Blob) => "blob:first-page-5");
const revokeObjectURL = vi.fn();
const image = { status: 200, data: new Blob(["webp"], { type: "image/webp" }) };
const pending = { status: 202, data: new Blob(["{}"], { type: "application/json" }) };
const notFound = Object.assign(new Error("404"), { response: { status: 404 } });

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
  forgetFirstPages();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const picture = (container: HTMLElement) => container.querySelector("img");

describe("PaperThumbnail", () => {
  it("shows the server's first-page image over the outline, as decoration", async () => {
    vi.mocked(recordsApi.firstPage).mockResolvedValue(image as never);
    const { container } = render(<PaperThumbnail recordId={5} available />);

    await waitFor(() => expect(picture(container)).toHaveAttribute("src", "blob:first-page-5"));
    expect(recordsApi.firstPage).toHaveBeenCalledWith(5, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(picture(container)).toHaveAttribute("alt", "");
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
  });

  it("keeps the outline and asks nothing when the record has no manuscript", () => {
    const { container } = render(<PaperThumbnail recordId={5} available={false} />);

    expect(picture(container)).toBeNull();
    expect(recordsApi.firstPage).not.toHaveBeenCalled();
  });

  it("asks once per session for a page it has, so going back to Discover is free", async () => {
    vi.mocked(recordsApi.firstPage).mockResolvedValue(image as never);
    const first = render(<PaperThumbnail recordId={5} available />);
    await waitFor(() => expect(picture(first.container)).not.toBeNull());
    first.unmount();

    const again = render(<PaperThumbnail recordId={5} available />);

    expect(picture(again.container)).toHaveAttribute("src", "blob:first-page-5");
    expect(recordsApi.firstPage).toHaveBeenCalledTimes(1);
  });

  it("keeps the outline while the page is being drawn, and asks again next time", async () => {
    vi.mocked(recordsApi.firstPage).mockResolvedValue(pending as never);
    const first = render(<PaperThumbnail recordId={5} available />);
    await waitFor(() => expect(recordsApi.firstPage).toHaveBeenCalledTimes(1));
    expect(picture(first.container)).toBeNull();
    first.unmount();

    render(<PaperThumbnail recordId={5} available />);

    await waitFor(() => expect(recordsApi.firstPage).toHaveBeenCalledTimes(2));
  });

  it("remembers a paper with no page to show, and doesn't ask again", async () => {
    vi.mocked(recordsApi.firstPage).mockRejectedValue(notFound);
    const first = render(<PaperThumbnail recordId={5} available />);
    await waitFor(() => expect(recordsApi.firstPage).toHaveBeenCalledTimes(1));
    first.unmount();

    const again = render(<PaperThumbnail recordId={5} available />);

    expect(picture(again.container)).toBeNull();
    expect(recordsApi.firstPage).toHaveBeenCalledTimes(1);
  });

  it("doesn't remember a failure it can't explain, such as being offline", async () => {
    vi.mocked(recordsApi.firstPage).mockRejectedValue(new Error("Network Error"));
    const first = render(<PaperThumbnail recordId={5} available />);
    await waitFor(() => expect(recordsApi.firstPage).toHaveBeenCalledTimes(1));
    first.unmount();

    render(<PaperThumbnail recordId={5} available />);

    await waitFor(() => expect(recordsApi.firstPage).toHaveBeenCalledTimes(2));
  });

  it("forgets every page, and frees its memory, when the session changes", async () => {
    vi.mocked(recordsApi.firstPage).mockResolvedValue(image as never);
    const first = render(<PaperThumbnail recordId={5} available />);
    await waitFor(() => expect(picture(first.container)).not.toBeNull());
    first.unmount();

    useAuthStore.setState((s) => ({ sessionEpoch: s.sessionEpoch + 1 }));
    render(<PaperThumbnail recordId={5} available />);

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:first-page-5");
    await waitFor(() => expect(recordsApi.firstPage).toHaveBeenCalledTimes(2));
  });
});
