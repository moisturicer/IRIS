/**
 * The in-app PDF reader (IR-335) — what a citation opens into.
 *
 * pdf.js itself is mocked throughout: jsdom has no real `<canvas>` 2D context
 * and cannot run the pdf.js worker, so nothing here exercises real rendering.
 * What is under test is this component's own logic around it -- fetching
 * through `apiClient` (never a bare URL, which would 401 against the
 * authenticated manuscript endpoint), scrolling to the right page, drawing
 * regions on the right page and no other, and the zoom/download affordances.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { render, screen, userEvent, waitFor } from "@/test/render";
import type { Region } from "@/types/ai";

import { PaperPdfReader } from "./PaperPdfReader";

const manuscriptBlob = vi.fn();
vi.mock("@/api/records", () => ({
  recordsApi: { manuscriptBlob: (...args: unknown[]) => manuscriptBlob(...(args as [])) },
}));

const loadPdfDocument = vi.fn();
const renderPageToCanvas = vi.fn();
vi.mock("@/lib/pdf", () => ({
  loadPdfDocument: (...args: unknown[]) => loadPdfDocument(...(args as [])),
  renderPageToCanvas: (...args: unknown[]) => renderPageToCanvas(...(args as [])),
}));

const downloadBlob = vi.fn();
vi.mock("@/lib/utils", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/utils")>()),
  downloadBlob: (...args: unknown[]) => downloadBlob(...(args as [])),
}));

function fakePage(pageNumber: number) {
  return { pageNumber };
}

function fakeDocument(numPages: number) {
  const pages = Array.from({ length: numPages }, (_, i) => fakePage(i + 1));
  return {
    numPages,
    getPage: vi.fn((n: number) => Promise.resolve(pages[n - 1])),
  };
}

const destroy = vi.fn(() => Promise.resolve());

function pdfBlob() {
  return new Blob(["%PDF-1.7 fake bytes"], { type: "application/pdf" });
}

beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = vi.fn();
  // jsdom has no `URL.createObjectURL`/`revokeObjectURL` -- the reader uses
  // both for the download affordance.
  URL.createObjectURL = vi.fn(() => "blob:mock-url");
  URL.revokeObjectURL = vi.fn();
  manuscriptBlob.mockResolvedValue({ data: pdfBlob() });
  loadPdfDocument.mockResolvedValue({ document: fakeDocument(3), destroy });
  renderPageToCanvas.mockReturnValue({
    promise: Promise.resolve({ width: 200, height: 300 }),
    cancel: vi.fn(),
  });
});

describe("loading the paper", () => {
  it("shows a loading state, then the page count once ready", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    expect(screen.getByText(/loading the paper/i)).toBeInTheDocument();
    expect(await screen.findByText("3 pages")).toBeInTheDocument();
  });

  it("fetches through apiClient, never a bare URL -- the endpoint requires auth", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    await waitFor(() => expect(manuscriptBlob).toHaveBeenCalledWith(7));
  });

  it("shows an error state rather than an empty reader when the fetch fails", async () => {
    manuscriptBlob.mockRejectedValue(new Error("network"));

    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    expect(await screen.findByText(/could not load the paper/i)).toBeInTheDocument();
  });

  it("shows an error state when the file is not a readable PDF", async () => {
    loadPdfDocument.mockRejectedValue(new Error("invalid PDF"));

    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    expect(await screen.findByText(/could not load the paper/i)).toBeInTheDocument();
  });
});

describe("scrolling to the cited page", () => {
  it("scrolls to the requested page once the document is ready", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={2} highlightRegions={[]} navKey="a" />,
    );

    await waitFor(() => expect(screen.getByText("3 pages")).toBeInTheDocument());
    await waitFor(() => {
      const target = document.querySelector('[data-page-number="2"]');
      expect(target?.scrollIntoView).toHaveBeenCalled();
    });
  });

  it("scrolls again on a repeated navigation to the same page", async () => {
    const { rerender } = render(
      <PaperPdfReader recordId={7} scrollToPage={2} highlightRegions={[]} navKey="first" />,
    );
    await waitFor(() => expect(screen.getByText("3 pages")).toBeInTheDocument());
    const target = document.querySelector('[data-page-number="2"]') as HTMLElement;
    vi.mocked(target.scrollIntoView).mockClear();

    // A second click on the very same citation still means "look here" --
    // only `navKey` changes, the page number does not.
    rerender(
      <PaperPdfReader recordId={7} scrollToPage={2} highlightRegions={[]} navKey="second" />,
    );

    await waitFor(() => expect(target.scrollIntoView).toHaveBeenCalled());
  });

  it("draws nothing when there is no page to scroll to", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    await waitFor(() => expect(screen.getByText("3 pages")).toBeInTheDocument());
    for (const el of document.querySelectorAll("[data-page-number]")) {
      expect(el.scrollIntoView).not.toHaveBeenCalled();
    }
  });
});

describe("citation highlights", () => {
  it("draws a region only on the page it names", async () => {
    const regions: Region[] = [
      { page: 2, left: 0.1, top: 0.1, right: 0.4, bottom: 0.2 },
    ];

    render(
      <PaperPdfReader recordId={7} scrollToPage={2} highlightRegions={regions} navKey="a" />,
    );
    await waitFor(() => expect(screen.getByText("3 pages")).toBeInTheDocument());

    const page1 = document.querySelector('[data-page-number="1"]');
    const page2 = document.querySelector('[data-page-number="2"]');
    expect(page1?.querySelector("[aria-hidden='true'] > div")).toBeNull();
    expect(page2?.querySelector("[aria-hidden='true'] > div")).not.toBeNull();
  });
});

describe("zoom controls", () => {
  it("zooming in and out changes the displayed percentage", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await waitFor(() => expect(screen.getByText("3 pages")).toBeInTheDocument());

    expect(screen.getByText("130%")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /zoom in/i }));
    expect(screen.getByText("150%")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /zoom out/i }));
    await userEvent.click(screen.getByRole("button", { name: /zoom out/i }));
    expect(screen.getByText("110%")).toBeInTheDocument();
  });
});

describe("downloading the paper", () => {
  it("offers a download once the file has loaded, with no second request", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    const button = await screen.findByRole("button", { name: /download/i });
    await userEvent.click(button);

    expect(downloadBlob).toHaveBeenCalledTimes(1);
    expect(manuscriptBlob).toHaveBeenCalledTimes(1);
  });

  it("disables download until the file has loaded", () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    expect(screen.getByRole("button", { name: /download/i })).toBeDisabled();
  });
});
