/**
 * The in-app PDF reader (IR-335) — what a citation opens into.
 *
 * pdf.js itself is mocked throughout: jsdom has no real `<canvas>` 2D context
 * and cannot run the pdf.js worker, so nothing here exercises real rendering.
 * What is under test is this component's own logic around it -- fetching
 * through `apiClient` (never a bare URL, which would 401 against the
 * authenticated manuscript endpoint), landing on the cited passage, drawing
 * regions on the right page and no other, and the zoom/download affordances.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { act, fireEvent, render, screen, userEvent, waitFor, within } from "@/test/render";
import type { TextRun } from "@/lib/pdf";
import type { Region } from "@/types/ai";

import { PaperPdfReader } from "./PaperPdfReader";

const manuscriptBlob = vi.fn();
vi.mock("@/api/records", () => ({
  recordsApi: { manuscriptBlob: (...args: unknown[]) => manuscriptBlob(...(args as [])) },
}));

const loadPdfDocument = vi.fn();
const renderPageToCanvas = vi.fn();
const pageText = vi.fn();
const renderTextLayer = vi.fn();
vi.mock("@/lib/pdf", () => ({
  loadPdfDocument: (...args: unknown[]) => loadPdfDocument(...(args as [])),
  renderPageToCanvas: (...args: unknown[]) => renderPageToCanvas(...(args as [])),
  pageText: (...args: unknown[]) => pageText(...(args as [])),
  renderTextLayer: (...args: unknown[]) => renderTextLayer(...(args as [])),
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

/** Each fake page's text, as `pageText` would extract it (IR-353). */
let paperText: TextRun[][] = [];

/** A run on its own line, `top` of the way down its page. */
function line(str: string, top: number): TextRun {
  return { str, eol: true, top, bottom: top + 0.02 };
}

/**
 * pdf.js's text layer, as far as the reader relies on it: one span per run,
 * in order, drawn into the container it is given.
 */
function fakeTextLayer(page: { pageNumber: number }, container: HTMLElement) {
  const spans = (paperText[page.pageNumber - 1] ?? []).map((run) => {
    const span = document.createElement("span");
    span.textContent = run.str;
    return span;
  });
  container.append(...spans);
  return { promise: Promise.resolve(), update: vi.fn(), cancel: vi.fn(), spans: () => spans };
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
  paperText = [[], [], []];
  pageText.mockImplementation((page: { pageNumber: number }) =>
    Promise.resolve(paperText[page.pageNumber - 1] ?? []),
  );
  renderTextLayer.mockImplementation(fakeTextLayer);
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

/**
 * Where a citation lands (IR-354): on the passage, not the page's top, and
 * clear of the fixed header and the reader's own toolbar.
 *
 * jsdom lays nothing out, so each test renders the reader, gives the pages,
 * the toolbar and the pane boxes, then follows a citation -- which is also
 * how it happens live: the reader is open when a citation in the chat
 * beside it is clicked.
 */
describe("landing on a cited passage (IR-354)", () => {
  const PASSAGE_LOW: Region[] = [{ page: 2, left: 0.1, top: 0.85, right: 0.9, bottom: 0.9 }];
  const PASSAGE_HIGH: Region[] = [{ page: 2, left: 0.1, top: 0.02, right: 0.9, bottom: 0.05 }];

  /**
   * The reader's parts. The paper is found by its role and name; the toolbar
   * and the pane have neither, so they are reached from what does -- the
   * toolbar is what holds the Download control, the pane what holds both.
   */
  async function openReader() {
    const view = render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="opened" />,
    );
    await screen.findByText("Page 1 / 3");
    const area = screen.getByRole("region", { name: "Paper, 3 pages" });
    return {
      ...view,
      area,
      toolbar: screen.getByRole("button", { name: "Download" }).parentElement as HTMLElement,
      pane: area.parentElement as HTMLElement,
    };
  }

  function follow(
    rerender: (ui: ReactElement) => void,
    regions: Region[],
    navKey = "followed",
  ) {
    rerender(
      <PaperPdfReader recordId={7} scrollToPage={2} highlightRegions={regions} navKey={navKey} />,
    );
  }

  describe("below lg, where the window scrolls", () => {
    let scrollBy: ReturnType<typeof vi.fn>;

    beforeEach(() => {
      scrollBy = vi.fn();
      vi.stubGlobal("scrollBy", scrollBy);
    });

    async function openAt() {
      const reader = await openReader();
      // Page 2 is 1000px tall, 1500px down. The toolbar has not stuck yet --
      // it is 400px down -- but it will have by the time the passage lands.
      placePages([
        { top: 484, height: 1000 },
        { top: 1500, height: 1000 },
        { top: 2516, height: 1000 },
      ]);
      vi.spyOn(reader.toolbar, "getBoundingClientRect").mockReturnValue(box(400, 44));
      return reader;
    }

    it("scrolls to the region's top, not the page's, below the header and the stuck toolbar", async () => {
      const { rerender } = await openAt();
      follow(rerender, PASSAGE_LOW);

      // The region starts at 1500 + 850 = 2350. It lands 48px of context
      // below the toolbar, which sticks at 122px and is 44px tall.
      await waitFor(() =>
        expect(scrollBy).toHaveBeenCalledWith({ top: 2350 - (122 + 44) - 48, behavior: "smooth" }),
      );
    });

    it("keeps a region at the top of the page clear of the header and toolbar too", async () => {
      const { rerender } = await openAt();
      follow(rerender, PASSAGE_HIGH);

      await waitFor(() =>
        expect(scrollBy).toHaveBeenCalledWith({ top: 1520 - (122 + 44) - 48, behavior: "smooth" }),
      );
    });

    it("lands on the page's top edge, below the toolbar, when the citation has no region", async () => {
      const { rerender } = await openAt();
      follow(rerender, []);

      await waitFor(() =>
        expect(scrollBy).toHaveBeenCalledWith({ top: 1500 - (122 + 44) - 16, behavior: "smooth" }),
      );
    });

    it("lands again when the same citation is followed a second time", async () => {
      const { rerender } = await openAt();
      follow(rerender, PASSAGE_LOW, "first");
      await waitFor(() => expect(scrollBy).toHaveBeenCalledTimes(1));

      // A second click on the very same citation still means "look here" --
      // only `navKey` changes, the page number does not.
      follow(rerender, PASSAGE_LOW, "second");

      await waitFor(() => expect(scrollBy).toHaveBeenCalledTimes(2));
    });

    it("lands again when the paper refits just after landing, as a scrollbar appearing makes it", async () => {
      const pane = measurePaneAs(602);
      const { rerender } = await openAt();
      follow(rerender, PASSAGE_LOW);
      await waitFor(() => expect(scrollBy).toHaveBeenCalledTimes(1));

      // The window's scrollbar appears once the pages are in, the pane
      // narrows, and the paper refits -- which moves the passage, and
      // cancels a smooth scroll still on its way to it.
      placePages([
        { top: 470, height: 970 },
        { top: 1456, height: 970 },
        { top: 2442, height: 970 },
      ]);
      act(() => pane.resizeTo(585));
      expect(await screen.findByText("194%")).toBeInTheDocument();

      // From where the passage is now: 1456 + 0.85 * 970 = 2280.5.
      await waitFor(() => expect(scrollBy).toHaveBeenCalledTimes(2));
      expect(scrollBy).toHaveBeenLastCalledWith({ top: 2280.5 - (122 + 44) - 48, behavior: "smooth" });
    });

    it("does not pull the reader back to the passage for a refit long after landing", async () => {
      const pane = measurePaneAs(602);
      const now = vi.spyOn(performance, "now").mockReturnValue(1_000);
      const { rerender } = await openAt();
      follow(rerender, PASSAGE_LOW);
      await waitFor(() => expect(scrollBy).toHaveBeenCalledTimes(1));

      // Minutes later the reader drags the window narrower.
      now.mockReturnValue(1_000 + 5 * 60_000);
      act(() => pane.resizeTo(585));
      expect(await screen.findByText("194%")).toBeInTheDocument();

      // Only the landing itself: no second one.
      expect(scrollBy.mock.calls.filter(([arg]) => typeof arg === "object")).toHaveLength(1);
    });

    it("does not scroll at all when there is no page to land on", async () => {
      await openAt();
      await waitFor(() => expect(screen.getAllByRole("group")).toHaveLength(3));

      expect(scrollBy).not.toHaveBeenCalled();
    });
  });

  describe("at lg, inside the contained pane", () => {
    it("brings the pane to rest below the header, then scrolls the pane to the region", async () => {
      // The one stub answers every query, reduced motion included.
      mediaQueryAt(true);
      const windowScrollBy = vi.fn();
      vi.stubGlobal("scrollBy", windowScrollBy);
      const reader = await openReader();
      const paneScrollBy = vi.fn();
      reader.area.scrollBy = paneScrollBy;

      // The pane is 400px down; it rests at 126px, under the header and the
      // view switch. Its toolbar ends at 444px, its scroll area at 1000px.
      vi.spyOn(reader.pane, "getBoundingClientRect").mockReturnValue(box(400, 600));
      vi.spyOn(reader.toolbar, "getBoundingClientRect").mockReturnValue(box(400, 44));
      vi.spyOn(reader.area, "getBoundingClientRect").mockReturnValue(box(444, 556));
      placePages([
        { top: 460, height: 1000 },
        { top: 1476, height: 1000 },
        { top: 2492, height: 1000 },
      ]);

      follow(reader.rerender, PASSAGE_LOW);

      await waitFor(() => expect(windowScrollBy).toHaveBeenCalledWith({ top: 400 - 126, behavior: "auto" }));
      // The region starts at 1476 + 850 = 2326; it lands 48px below the
      // pane's toolbar, measured in the pane, so the window's own scroll
      // (which moves both) does not change it.
      expect(paneScrollBy).toHaveBeenCalledWith({ top: 2326 - 444 - 48, behavior: "auto" });
    });
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
  const observers = new Set<{ report: (width: number) => void }>();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      private readonly targets = new Set<Element>();
      constructor(private readonly callback: ResizeObserverCallback) {
        observers.add(this);
      }
      report(next: number) {
        this.targets.forEach((target) =>
          this.callback(
            [{ target, contentRect: { width: next } } as unknown as ResizeObserverEntry],
            this as unknown as ResizeObserver,
          ),
        );
      }
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
  return Object.assign(watching, {
    /** The pane is now `next` wide, as when a scrollbar appears beside it. */
    resizeTo: (next: number) => observers.forEach((observer) => observer.report(next)),
  });
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

/** A box `height` tall whose top is at `top`, as jsdom never measures one. */
function box(top: number, height: number) {
  return { top, bottom: top + height, height, left: 0, right: 0, width: 0, x: 0, y: top, toJSON: () => ({}) } as DOMRect;
}

/** Gives each page a box, since jsdom lays nothing out. */
function placePages(boxes: { top: number; height: number }[]) {
  boxes.forEach(({ top, height }, i) => {
    const page = screen.getByRole("group", { name: `Page ${i + 1}` });
    vi.spyOn(page, "getBoundingClientRect").mockImplementation(() => box(top, height));
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

/**
 * Find in this paper (IR-353): the open PDF's own text, searched in the
 * browser. The text layer and the extracted text are `lib/pdf`'s, mocked
 * above; what is under test is the reader's find around them.
 */
describe("find in this paper (IR-353)", () => {
  const PAPER: TextRun[][] = [
    [line("Vision-language-action models", 0.1), line("for Robot control.", 0.13)],
    [line("Nothing to see here.", 0.2)],
    [line("A robot arm, and another ROBOT.", 0.5)],
  ];

  async function openPaper() {
    paperText = PAPER;
    render(<PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />);
    await screen.findByText("Page 1 / 3");
  }

  async function openFind() {
    await userEvent.click(screen.getByRole("button", { name: "Find in this paper" }));
    const input = await screen.findByRole("searchbox", { name: "Find in this paper" });
    await waitFor(() => expect(input).toHaveFocus());
    return input;
  }

  /** Find's match status, which is announced as it changes. */
  const findStatus = () => within(screen.getByRole("search")).getByRole("status");

  /** The words marked as matches on a page, and which one is current. */
  function marksOn(pageNumber: number) {
    const page = screen.getByRole("group", { name: `Page ${pageNumber}` });
    return Array.from(page.querySelectorAll("mark")).map((mark) => ({
      text: mark.textContent,
      current: mark.classList.contains("find-hit-current"),
    }));
  }

  /** The reader's toolbar: what holds the Download control. */
  const toolbar = () => screen.getByRole("button", { name: "Download" }).parentElement as HTMLElement;

  it("is a find of its own in the reader's toolbar, apart from the header's search", async () => {
    await openPaper();
    const input = await openFind();

    expect(within(screen.getByRole("search")).getByRole("searchbox")).toBe(input);
    expect(input).toHaveAttribute("placeholder", "Find in this paper");
    expect(screen.getByRole("button", { name: "Find in this paper" })).toHaveAttribute("aria-expanded", "true");
  });

  it("opens on Ctrl+F or Cmd+F while the reader has focus", async () => {
    await openPaper();
    const paper = screen.getByRole("region", { name: "Paper, 3 pages" });

    paper.focus();
    fireEvent.keyDown(paper, { key: "f", ctrlKey: true });
    await waitFor(() => expect(screen.getByRole("searchbox", { name: "Find in this paper" })).toHaveFocus());

    await userEvent.keyboard("{Escape}");
    fireEvent.keyDown(paper, { key: "f", metaKey: true });
    expect(await screen.findByRole("searchbox", { name: "Find in this paper" })).toBeInTheDocument();
  });

  it("counts every match on every page, whatever its case", async () => {
    await openPaper();
    await userEvent.type(await openFind(), "robot");

    await waitFor(() => expect(findStatus()).toHaveTextContent("1 of 3"));
    expect(marksOn(1)).toEqual([{ text: "Robot", current: true }]);
    expect(marksOn(2)).toEqual([]);
    expect(marksOn(3)).toEqual([
      { text: "robot", current: false },
      { text: "ROBOT", current: false },
    ]);
  });

  it("moves to the next match on Enter and back on Shift+Enter, wrapping at the ends", async () => {
    await openPaper();
    await userEvent.type(await openFind(), "robot");
    await waitFor(() => expect(findStatus()).toHaveTextContent("1 of 3"));

    await userEvent.keyboard("{Enter}");
    expect(findStatus()).toHaveTextContent("2 of 3");
    expect(marksOn(3)[0].current).toBe(true);

    await userEvent.keyboard("{Enter}{Enter}");
    expect(findStatus()).toHaveTextContent("1 of 3");

    await userEvent.keyboard("{Shift>}{Enter}{/Shift}");
    expect(findStatus()).toHaveTextContent("3 of 3");
    expect(marksOn(3)[1].current).toBe(true);
  });

  it("moves with the next and previous controls too", async () => {
    await openPaper();
    await userEvent.type(await openFind(), "robot");
    await waitFor(() => expect(findStatus()).toHaveTextContent("1 of 3"));

    await userEvent.click(screen.getByRole("button", { name: "Next match" }));
    expect(findStatus()).toHaveTextContent("2 of 3");
    await userEvent.click(screen.getByRole("button", { name: "Previous match" }));
    expect(findStatus()).toHaveTextContent("1 of 3");
  });

  it("finds a phrase that runs over a line's end", async () => {
    await openPaper();
    await userEvent.type(await openFind(), "models for robot");

    await waitFor(() => expect(findStatus()).toHaveTextContent("1 of 1"));
    expect(marksOn(1).map((mark) => mark.text)).toEqual(["models", "for Robot"]);
  });

  it("says so when nothing matches", async () => {
    await openPaper();
    await userEvent.type(await openFind(), "quantum");

    await waitFor(() => expect(findStatus()).toHaveTextContent("No matches"));
    expect(screen.getByRole("button", { name: "Next match" })).toBeDisabled();
  });

  it("says a scanned paper has no searchable text, rather than that nothing matches", async () => {
    render(<PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />);
    await screen.findByText("Page 1 / 3");
    await openFind();

    await waitFor(() => expect(findStatus()).toHaveTextContent("This paper has no searchable text"));
    // Nothing to step through, so the textbox keeps the row to itself.
    expect(screen.queryByRole("button", { name: "Next match" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Previous match" })).not.toBeInTheDocument();
  });

  it("takes typing before every page's text is in, and fills in the count as it arrives", async () => {
    let releasePage3: (runs: TextRun[]) => void = () => {};
    paperText = PAPER;
    pageText.mockImplementation((page: { pageNumber: number }) =>
      page.pageNumber === 3
        ? new Promise<TextRun[]>((resolve) => {
            releasePage3 = resolve;
          })
        : Promise.resolve(PAPER[page.pageNumber - 1]),
    );
    render(<PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />);
    await screen.findByText("Page 1 / 3");

    await userEvent.type(await openFind(), "robot");
    await waitFor(() => expect(findStatus()).toHaveTextContent("1 of 1…"));

    await act(async () => releasePage3(PAPER[2]));
    await waitFor(() => expect(findStatus()).toHaveTextContent("1 of 3"));
  });

  it("scrolls a match out of view to rest below the header and the toolbar", async () => {
    const scrollBy = vi.fn();
    vi.stubGlobal("scrollBy", scrollBy);
    await openPaper();
    const input = await openFind();
    // Below lg the window scrolls. Page 3 is 1000px tall, 2516px down; the
    // toolbar, with find open inside it, is 96px tall once stuck at 122px.
    placePages([
      { top: 484, height: 1000 },
      { top: 1500, height: 1000 },
      { top: 2516, height: 1000 },
    ]);
    vi.spyOn(toolbar(), "getBoundingClientRect").mockReturnValue(box(122, 96));

    await userEvent.type(input, "arm");

    // Page 3's line is half way down: 2516 + 500 = 3016. It lands 48px of
    // context below the toolbar, at once rather than smoothly.
    await waitFor(() =>
      expect(scrollBy).toHaveBeenCalledWith({ top: 3016 - (122 + 96) - 48, behavior: "auto" }),
    );
  });

  it("leaves a match already in view where it is", async () => {
    const scrollBy = vi.fn();
    vi.stubGlobal("scrollBy", scrollBy);
    await openPaper();
    const input = await openFind();
    // Page 1 fills the view: its first line is at 300 + 100 = 400px.
    placePages([
      { top: 300, height: 1000 },
      { top: 1316, height: 1000 },
      { top: 2332, height: 1000 },
    ]);
    vi.spyOn(toolbar(), "getBoundingClientRect").mockReturnValue(box(122, 96));

    await userEvent.type(input, "vision");
    await waitFor(() => expect(findStatus()).toHaveTextContent("1 of 1"));

    expect(scrollBy).not.toHaveBeenCalled();
  });

  it("closes on Esc, clearing its highlights and returning focus", async () => {
    await openPaper();
    await userEvent.type(await openFind(), "robot");
    await waitFor(() => expect(findStatus()).toHaveTextContent("1 of 3"));

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("search")).not.toBeInTheDocument();
    expect([1, 2, 3].flatMap(marksOn)).toEqual([]);
    expect(screen.getByRole("button", { name: "Find in this paper" })).toHaveFocus();
  });

  it("returns focus to the paper when it was opened from there", async () => {
    await openPaper();
    const paper = screen.getByRole("region", { name: "Paper, 3 pages" });
    paper.focus();
    fireEvent.keyDown(paper, { key: "f", ctrlKey: true });
    await waitFor(() => expect(screen.getByRole("searchbox")).toHaveFocus());

    await userEvent.keyboard("{Escape}");

    expect(paper).toHaveFocus();
  });

  it("draws the page's text as a layer, with a citation's highlight still over it", async () => {
    paperText = PAPER;
    const regions: Region[] = [{ page: 3, left: 0.1, top: 0.5, right: 0.9, bottom: 0.52 }];
    render(<PaperPdfReader recordId={7} scrollToPage={3} highlightRegions={regions} navKey="a" />);
    const page3 = await screen.findByRole("group", { name: "Page 3" });

    // The text is in the page, so it can be selected and copied.
    expect(await within(page3).findByText("A robot arm, and another ROBOT.")).toBeInTheDocument();

    await userEvent.type(await openFind(), "robot");
    await waitFor(() => expect(marksOn(3)).toHaveLength(2));
    // The overlay is the page's last layer, so it draws above the text. It
    // is `aria-hidden` (CitationOverlay.tsx), so no accessible query
    // reaches it; this is scoped to the page found accessibly above.
    expect(page3.lastElementChild).toHaveAttribute("aria-hidden", "true");
    expect(page3.lastElementChild?.children).toHaveLength(1);
  });

  it("has no serious or critical violations with find open and matches marked", async () => {
    paperText = PAPER;
    const { container } = render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await screen.findByText("Page 1 / 3");
    await userEvent.type(await openFind(), "robot");
    await waitFor(() => expect(findStatus()).toHaveTextContent("1 of 3"));

    await expectNoBlockingA11yViolations(container);
  });
});
