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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { act, fireEvent, render, screen, userEvent, waitFor } from "@/test/render";
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
  // A 300x400 page at scale 1, like pdf.js's viewport arithmetic.
  pageSize: (_page: unknown, scale: number) => ({ width: 300 * scale, height: 400 * scale }),
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
    promise: Promise.resolve(),
    cancel: vi.fn(),
  });
});

// ResizeObserver and scrollBy are stubbed per test; none may leak into the next.
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("loading the paper", () => {
  it("shows a loading state, then where the reader is once ready", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    expect(screen.getByText(/loading the paper/i)).toBeInTheDocument();
    expect(await screen.findByText("Page 1 / 3")).toBeInTheDocument();
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

  it("offers to try again after a failed fetch, and loads the paper when it succeeds", async () => {
    manuscriptBlob.mockRejectedValueOnce(new Error("network"));

    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await userEvent.click(await screen.findByRole("button", { name: /try again/i }));

    expect(await screen.findByText("Page 1 / 3")).toBeInTheDocument();
    expect(manuscriptBlob).toHaveBeenCalledTimes(2);
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

    const target = await screen.findByRole("group", { name: "Page 2" });
    await waitFor(() => expect(target.scrollIntoView).toHaveBeenCalled());
  });

  it("scrolls again on a repeated navigation to the same page", async () => {
    const { rerender } = render(
      <PaperPdfReader recordId={7} scrollToPage={2} highlightRegions={[]} navKey="first" />,
    );
    const target = await screen.findByRole("group", { name: "Page 2" });
    await waitFor(() => expect(target.scrollIntoView).toHaveBeenCalled());
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

    await waitFor(() => expect(screen.getAllByRole("group")).toHaveLength(3));
    for (const page of screen.getAllByRole("group")) {
      expect(page.scrollIntoView).not.toHaveBeenCalled();
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
    const page1 = await screen.findByRole("group", { name: "Page 1" });
    const page2 = await screen.findByRole("group", { name: "Page 2" });

    // The highlight box itself is `aria-hidden` (CitationOverlay.tsx) --
    // decorative for a sighted reader scanning the rendered page, and
    // meaningless to a screen reader, which cannot read a `<canvas>` at all.
    // There is no accessible-tree query for "is a decorative box drawn
    // here", so this one assertion reaches past it, scoped to the page
    // `getByRole` above already found accessibly.
    expect(page1.querySelector("[aria-hidden='true'] > div")).toBeNull();
    expect(page2.querySelector("[aria-hidden='true'] > div")).not.toBeNull();
  });
});

describe("zoom controls", () => {
  it("zooming in and out changes the displayed percentage", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await screen.findByText("Page 1 / 3");

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

describe("accessibility", () => {
  it("has no serious or critical violations while loading", async () => {
    const { container } = render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    await expectNoBlockingA11yViolations(container);
  });

  it("has no serious or critical violations once the reader is ready, with a highlight drawn", async () => {
    const regions: Region[] = [{ page: 1, left: 0.1, top: 0.1, right: 0.4, bottom: 0.2 }];
    const { container } = render(
      <PaperPdfReader recordId={7} scrollToPage={1} highlightRegions={regions} navKey="a" />,
    );

    await screen.findByText("Page 1 / 3");
    await expectNoBlockingA11yViolations(container);
  });

  it("has no serious or critical violations in the error state", async () => {
    manuscriptBlob.mockRejectedValue(new Error("network"));
    const { container } = render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    await screen.findByText(/could not load the paper/i);
    await expectNoBlockingA11yViolations(container);
  });
});

/**
 * jsdom has no ResizeObserver and no layout. This one reports a fixed width
 * for whatever it observes, which is all the reader asks of it.
 */
function measurePaneAs(width: number) {
  const watching = new Set<Element>();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      private readonly targets = new Set<Element>();
      constructor(private readonly callback: ResizeObserverCallback) {}
      observe(target: Element) {
        this.targets.add(target);
        watching.add(target);
        this.callback(
          [{ target, contentRect: { width } } as unknown as ResizeObserverEntry],
          this as unknown as ResizeObserver,
        );
      }
      unobserve(target: Element) {
        this.targets.delete(target);
        watching.delete(target);
      }
      disconnect() {
        this.targets.forEach((target) => watching.delete(target));
        this.targets.clear();
      }
    },
  );
  /** The elements some observer is still watching. */
  return watching;
}

/**
 * A `matchMedia` whose one query can be flipped, as crossing a breakpoint
 * does. jsdom has none.
 */
function mediaQueryAt(initiallyMatches: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  let matches = initiallyMatches;
  vi.stubGlobal("matchMedia", (query: string) => ({
    get matches() { return matches; },
    media: query,
    addEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => listeners.delete(listener),
  }));
  return (next: boolean) => {
    matches = next;
    listeners.forEach((listener) => listener({ matches: next } as MediaQueryListEvent));
  };
}

/** Gives each page a box, since jsdom lays nothing out. */
function placePages(boxes: { top: number; height: number }[]) {
  boxes.forEach((box, i) => {
    const page = screen.getByRole("group", { name: `Page ${i + 1}` });
    vi.spyOn(page, "getBoundingClientRect").mockImplementation(
      () => ({ top: box.top, bottom: box.top + box.height, height: box.height, left: 0, right: 0, width: 0, x: 0, y: box.top, toJSON: () => ({}) }) as DOMRect,
    );
  });
}

describe("fitting the paper to its pane (IR-352)", () => {
  it("opens fitted to the pane's width", async () => {
    // (602 - the page's 2px border) / 300px at scale 1 = 2.0.
    measurePaneAs(602);
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    await screen.findByText("Page 1 / 3");
    expect(screen.getByText("200%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fit to width" })).toHaveAttribute("aria-pressed", "true");
  });

  it("leaves fit when the reader zooms, and the fit control restores it", async () => {
    measurePaneAs(602);
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await screen.findByText("Page 1 / 3");

    await userEvent.click(screen.getByRole("button", { name: /zoom in/i }));
    expect(screen.getByText("220%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fit to width" })).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(screen.getByRole("button", { name: "Fit to width" }));
    expect(screen.getByText("200%")).toBeInTheDocument();
  });

  it("keeps the default zoom when the pane cannot be measured", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    await screen.findByText("Page 1 / 3");
    expect(screen.getByText("130%")).toBeInTheDocument();
  });

  it("sizes each page from its own dimensions at the current zoom", async () => {
    measurePaneAs(602);
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await screen.findByText("Page 1 / 3");

    // The box is sized before the canvas paints, so the layout does not jump
    // and a reading position can be restored in the same frame.
    expect(screen.getByRole("group", { name: "Page 1" })).toHaveStyle({ width: "600px", height: "800px" });
  });
});

describe("where the reader is (IR-352)", () => {
  it("follows the page under the top of the view as the paper scrolls", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await screen.findByText("Page 1 / 3");

    placePages([
      { top: -900, height: 520 },
      { top: -364, height: 520 },
      { top: 172, height: 520 },
    ]);
    fireEvent.scroll(window);

    expect(await screen.findByText("Page 2 / 3")).toBeInTheDocument();
  });

  it("keeps the reader at the same place in the page when the zoom changes", async () => {
    const scrollBy = vi.fn();
    vi.stubGlobal("scrollBy", scrollBy);
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await screen.findByText("Page 1 / 3");

    // Half-way down page 2 when the reader zooms in...
    placePages([
      { top: -780, height: 520 },
      { top: -260, height: 520 },
      { top: 276, height: 520 },
    ]);
    fireEvent.scroll(window);
    await screen.findByText("Page 2 / 3");

    // ...after which page 2 is taller and has moved.
    placePages([
      { top: -1000, height: 600 },
      { top: -380, height: 600 },
      { top: 236, height: 600 },
    ]);
    await userEvent.click(screen.getByRole("button", { name: /zoom in/i }));

    // Half-way down the new page 2 is at -380 + 300 = -80: scroll up 80px.
    await waitFor(() => expect(scrollBy).toHaveBeenCalledWith(0, -80));
  });
});

describe("keeping its place through a layout change (IR-352)", () => {
  it("keeps watching the pane's width after a failed load is retried", async () => {
    const watching = measurePaneAs(602);
    manuscriptBlob.mockRejectedValueOnce(new Error("network"));
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    await userEvent.click(await screen.findByRole("button", { name: /try again/i }));
    const region = await screen.findByRole("region", { name: "Paper, 3 pages" });

    // The pane the reader is showing now, not the one the error replaced.
    expect(watching.has(region)).toBe(true);
    expect([...watching].every((el) => el.isConnected)).toBe(true);
  });

  it("puts the reader back in place when the window crosses into the contained layout", async () => {
    const crossTo = mediaQueryAt(false);
    const scrollBy = vi.fn();
    vi.stubGlobal("scrollBy", scrollBy);
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await screen.findByText("Page 1 / 3");

    // A quarter of the way down page 2, reading in the scrolling page...
    placePages([
      { top: -650, height: 520 },
      { top: -130, height: 520 },
      { top: 406, height: 520 },
    ]);
    fireEvent.scroll(window);
    await screen.findByText("Page 2 / 3");

    // ...the window widens past 1024px and the same page is now elsewhere.
    placePages([
      { top: 20, height: 520 },
      { top: 556, height: 520 },
      { top: 1092, height: 520 },
    ]);
    act(() => crossTo(true));

    // A quarter down the moved page 2 is at 556 + 130 = 686.
    await waitFor(() => expect(scrollBy).toHaveBeenCalledWith(0, 686));
  });
});

describe("the paper as a scrollable region (IR-352)", () => {
  it("is a named region a keyboard user can focus and scroll", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    const region = await screen.findByRole("region", { name: "Paper, 3 pages" });
    expect(region).toHaveAttribute("tabindex", "0");
  });
});
