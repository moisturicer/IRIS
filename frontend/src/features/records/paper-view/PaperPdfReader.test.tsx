/**
 * The in-app PDF reader (IR-335) — what a citation opens into.
 *
 * pdf.js itself is mocked throughout: jsdom has no real `<canvas>` 2D context
 * and cannot run the pdf.js worker, so nothing here exercises real rendering.
 * What is under test is this component's own logic around it -- fetching
 * through `apiClient` (never a bare URL, which would 401 against the
 * authenticated manuscript endpoint), landing on the cited passage, drawing
 * regions on the right page and no other, the zoom affordances, and the
 * download control the caller hands it.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import type { ComponentProps, ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { act, fireEvent, render, screen, userEvent, waitFor, within } from "@/test/render";
import type { TextRun } from "@/lib/pdf";
import type { Region } from "@/types/ai";

import { CORNER_CLEARANCE_CLASS } from "./AskIrisFab";
import { PaperPdfReader } from "./PaperPdfReader";
import type { Passage } from "./threads/passage";
import { ReaderAnnotationsContext } from "./threads/readerAnnotations";
import { PublishDetailsPreview } from "@/features/publish/PublishDetailsPreview";
import { useAuthStore } from "@/store/auth.store";
import { PANE_TOP_PX, READER_TOOLBAR_TOP_PX } from "./paneLayout";
import { MAX_LIVE_PAGES } from "./readerGeometry";

const manuscriptBlob = vi.fn();
const versionManuscriptBlob = vi.fn();
vi.mock("@/api/records", () => ({
  recordsApi: {
    manuscriptBlob: (...args: unknown[]) => manuscriptBlob(...(args as [])),
    versionManuscriptBlob: (...args: unknown[]) => versionManuscriptBlob(...(args as [])),
  },
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
  // jsdom has no `URL.createObjectURL`/`revokeObjectURL`; stubbed so
  // nothing the reader renders trips over them.
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

    // With an abort signal (IR-565): a reader that moves on cancels the fetch.
    await waitFor(() => expect(manuscriptBlob).toHaveBeenCalledWith(7, { signal: expect.any(AbortSignal) }));
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

describe("Publish Details with the authenticated reader (IR-834)", () => {
  const details = <label>Title<input defaultValue="Original title" /></label>;

  it("keeps Details editable when access fails and Retry loads the accepted source", async () => {
    manuscriptBlob.mockRejectedValueOnce(new Error("forbidden"));
    const user = userEvent.setup();
    render(<PublishDetailsPreview recordId={42} sourceKey={1}>{details}</PublishDetailsPreview>);

    const title = screen.getByRole("textbox", { name: "Title" });
    await user.clear(title);
    await user.type(title, "My revised title");
    const preview = screen.getByRole("region", { name: "Manuscript preview" });
    expect(await within(preview).findByText(/could not load the paper/i)).toBeInTheDocument();
    expect(within(preview).queryByText("Page 1 / 3")).not.toBeInTheDocument();

    await user.click(within(preview).getByRole("button", { name: /try again/i }));
    expect(await within(preview).findByText("Page 1 / 3")).toBeInTheDocument();
    expect(title).toHaveValue("My revised title");
    expect(manuscriptBlob).toHaveBeenCalledWith(42, { signal: expect.any(AbortSignal) });
  });

  it("aborts the old request and ignores its late reply after an accepted replacement", async () => {
    let resolveOld!: (value: { data: Blob }) => void;
    manuscriptBlob
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }))
      .mockResolvedValueOnce({ data: pdfBlob() });
    const { rerender } = render(
      <PublishDetailsPreview recordId={42} sourceKey={1}>{details}</PublishDetailsPreview>,
    );
    await waitFor(() => expect(manuscriptBlob).toHaveBeenCalledTimes(1));
    const oldSignal = manuscriptBlob.mock.calls[0][1].signal as AbortSignal;

    rerender(<PublishDetailsPreview recordId={42} sourceKey={2}>{details}</PublishDetailsPreview>);
    expect(oldSignal.aborted).toBe(true);
    expect(await screen.findByText("Page 1 / 3")).toBeInTheDocument();
    await act(async () => { resolveOld({ data: pdfBlob() }); });

    expect(manuscriptBlob).toHaveBeenCalledTimes(2);
    expect(loadPdfDocument).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("textbox", { name: "Title" })).toHaveValue("Original title");
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
   * The reader's parts, found by role and name; the pane has neither, so it
   * is reached from the paper it holds.
   */
  async function openReader(contained = false) {
    const view = render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="opened" contained={contained} />,
    );
    await screen.findByText("Page 1 / 3");
    const area = screen.getByRole("region", { name: "Paper, 3 pages" });
    return {
      ...view,
      area,
      toolbar: screen.getByRole("toolbar", { name: "Paper tools" }),
      pane: area.parentElement as HTMLElement,
    };
  }

  function follow(
    rerender: (ui: ReactElement) => void,
    regions: Region[],
    navKey = "followed",
    contained = false,
  ) {
    rerender(
      <PaperPdfReader recordId={7} scrollToPage={2} highlightRegions={regions} navKey={navKey} contained={contained} />,
    );
  }

  describe("in a narrower workspace, where the window scrolls", () => {
    let scrollBy: ReturnType<typeof vi.fn>;

    beforeEach(() => {
      scrollBy = vi.fn();
      vi.stubGlobal("scrollBy", scrollBy);
    });

    /** The window scrolls that land a citation, as against keeping the reader's place. */
    const landings = () => scrollBy.mock.calls.filter(([arg]) => typeof arg === "object");

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
      // below the toolbar, which sticks at READER_TOOLBAR_TOP_PX and is 44px tall.
      await waitFor(() =>
        expect(scrollBy).toHaveBeenCalledWith({ top: 2350 - (READER_TOOLBAR_TOP_PX + 44) - 48, behavior: "smooth" }),
      );
    });

    it("keeps a region at the top of the page clear of the header and toolbar too", async () => {
      const { rerender } = await openAt();
      follow(rerender, PASSAGE_HIGH);

      await waitFor(() =>
        expect(scrollBy).toHaveBeenCalledWith({ top: 1520 - (READER_TOOLBAR_TOP_PX + 44) - 48, behavior: "smooth" }),
      );
    });

    it("lands on the page's top edge, below the toolbar, when the citation has no region", async () => {
      const { rerender } = await openAt();
      follow(rerender, []);

      await waitFor(() =>
        expect(scrollBy).toHaveBeenCalledWith({ top: 1500 - (READER_TOOLBAR_TOP_PX + 44) - 16, behavior: "smooth" }),
      );
    });

    it("ends a tall passage above a bar stuck over the window's bottom, giving up context first (IR-477)", async () => {
      vi.stubGlobal("innerHeight", 740);
      const { rerender } = await openAt();
      // 500px of passage from 1500 + 100 = 1600. The band runs from under the
      // toolbar (READER_TOOLBAR_TOP_PX + 44 = 108) to the bar's top, 740 - 112 =
      // 628: 520px. With 48px of context its end would be 28px under the bar,
      // so it keeps only the 20px that fit.
      const TALL: Region[] = [{ page: 2, left: 0.1, top: 0.1, right: 0.9, bottom: 0.6 }];
      rerender(
        <PaperPdfReader recordId={7} scrollToPage={2} highlightRegions={TALL} navKey="followed" bottomInset={112} />,
      );

      const bandTop = READER_TOOLBAR_TOP_PX + 44;
      await waitFor(() =>
        expect(scrollBy).toHaveBeenCalledWith({ top: 1600 - bandTop - 20, behavior: "smooth" }),
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
      await waitFor(() => expect(landings()).toHaveLength(1));

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

      // From where the passage is now: 1456 + 0.85 * 970 = 2280.5. The
      // reader's place is also kept through the refit (`scrollBy(0, n)`,
      // IR-352); the landing comes after it, so it is the last word.
      await waitFor(() => expect(landings()).toHaveLength(2));
      expect(scrollBy).toHaveBeenLastCalledWith({ top: 2280.5 - (READER_TOOLBAR_TOP_PX + 44) - 48, behavior: "smooth" });
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

  describe("in a reading-wide workspace, inside the contained pane (IR-569)", () => {
    it("brings the pane to rest below the header, then scrolls the pane to the region", async () => {
      // Reduced motion, so the landing is instant.
      mediaQueryAt(true);
      const windowScrollBy = vi.fn();
      vi.stubGlobal("scrollBy", windowScrollBy);
      const reader = await openReader(true);
      const paneScrollBy = vi.fn();
      reader.area.scrollBy = paneScrollBy;

      // The pane is 400px down; it rests at PANE_TOP_PX, under the view
      // reading header. Its toolbar ends at 444px, its scroll area at 1000px.
      vi.spyOn(reader.pane, "getBoundingClientRect").mockReturnValue(box(400, 600));
      vi.spyOn(reader.toolbar, "getBoundingClientRect").mockReturnValue(box(400, 44));
      vi.spyOn(reader.area, "getBoundingClientRect").mockReturnValue(box(444, 556));
      placePages([
        { top: 460, height: 1000 },
        { top: 1476, height: 1000 },
        { top: 2492, height: 1000 },
      ]);

      follow(reader.rerender, PASSAGE_LOW, "followed", true);

      await waitFor(() => expect(windowScrollBy).toHaveBeenCalledWith({ top: 400 - PANE_TOP_PX, behavior: "auto" }));
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

describe("keeping clear of the corner buttons (IR-1079)", () => {
  it("leaves room under the last page for Notes and Ask IRIS when the caller asks", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" contained fill clearCorner />,
    );

    expect(await screen.findByRole("region", { name: "Paper, 3 pages" })).toHaveClass(CORNER_CLEARANCE_CLASS);
  });

  it("adds none when the caller has no corner buttons over it", async () => {
    render(<PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" contained fill />);

    expect(await screen.findByRole("region", { name: "Paper, 3 pages" })).not.toHaveClass(CORNER_CLEARANCE_CLASS);
  });
});

describe("zoom controls", () => {
  it("zooming in and out changes the displayed percentage", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await screen.findByText("Page 1 / 3");

    expect(screen.getByText("140%")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /zoom in/i }));
    expect(screen.getByText("160%")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /zoom out/i }));
    await userEvent.click(screen.getByRole("button", { name: /zoom out/i }));
    expect(screen.getByText("120%")).toBeInTheDocument();
  });
});

describe("saving a copy (IR-677)", () => {
  // The reader used to save the bytes it had fetched. Under ADR-048 every
  // saved copy goes through the download route, which marks it (IR-676), so
  // the reader holds the caller's control and saves nothing itself.
  it("shows the caller's download control in its toolbar", async () => {
    render(
      <PaperPdfReader
        recordId={7}
        scrollToPage={null}
        highlightRegions={[]}
        navKey="a"
        downloadControl={<button type="button">Request download</button>}
      />,
    );
    await screen.findByText("Page 1 / 3");

    const toolbar = screen.getByRole("toolbar", { name: "Paper tools" });
    expect(within(toolbar).getByRole("button", { name: "Request download" })).toBeInTheDocument();
  });

  it("offers no download of its own", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await screen.findByText("Page 1 / 3");

    expect(screen.queryByRole("button", { name: /download/i })).not.toBeInTheDocument();
    expect(downloadBlob).not.toHaveBeenCalled();
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

  it("keeps the default zoom, 140%, when the pane cannot be measured", async () => {
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    await screen.findByText("Page 1 / 3");
    expect(screen.getByText("140%")).toBeInTheDocument();
  });

  it("opens at 140% in a pane wide enough for it, with Fit one press away (IR-569)", async () => {
    // (782 - the page's 2px border) / 300px at scale 1 = 2.6, held to the 240% maximum.
    measurePaneAs(782);
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    await screen.findByText("Page 1 / 3");
    expect(screen.getByText("140%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fit to width" })).toHaveAttribute("aria-pressed", "false");

    await userEvent.click(screen.getByRole("button", { name: "Fit to width" }));
    expect(screen.getByText("240%")).toBeInTheDocument();
  });

  it("opens fitted in a pane narrower than 640px, where 140% would run past its edge (IR-569)", async () => {
    measurePaneAs(602);
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );

    await screen.findByText("Page 1 / 3");
    expect(screen.getByText("200%")).toBeInTheDocument();
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

  it("puts the reader back in place when the workspace crosses into the contained layout", async () => {
    const scrollBy = vi.fn();
    vi.stubGlobal("scrollBy", scrollBy);
    const { rerender } = render(
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

    // ...the workspace widens to reading-wide and the same page is now elsewhere.
    placePages([
      { top: 20, height: 520 },
      { top: 556, height: 520 },
      { top: 1092, height: 520 },
    ]);
    rerender(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" contained />,
    );

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

  async function openPaper(bottomInset?: number) {
    paperText = PAPER;
    render(<PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" bottomInset={bottomInset} />);
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

  /** The reader's toolbar. */
  const toolbar = () => screen.getByRole("toolbar", { name: "Paper tools" });

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
    // toolbar, with find open inside it, is 96px tall once stuck at
    // READER_TOOLBAR_TOP_PX.
    placePages([
      { top: 484, height: 1000 },
      { top: 1500, height: 1000 },
      { top: 2516, height: 1000 },
    ]);
    vi.spyOn(toolbar(), "getBoundingClientRect").mockReturnValue(box(READER_TOOLBAR_TOP_PX, 96));

    await userEvent.type(input, "arm");

    // Page 3's line is half way down: 2516 + 500 = 3016. It lands 48px of
    // context below the toolbar, at once rather than smoothly.
    await waitFor(() =>
      expect(scrollBy).toHaveBeenCalledWith({ top: 3016 - (READER_TOOLBAR_TOP_PX + 96) - 48, behavior: "auto" }),
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
    vi.spyOn(toolbar(), "getBoundingClientRect").mockReturnValue(box(READER_TOOLBAR_TOP_PX, 96));

    await userEvent.type(input, "vision");
    await waitFor(() => expect(findStatus()).toHaveTextContent("1 of 1"));

    expect(scrollBy).not.toHaveBeenCalled();
  });

  it("treats a match under a bar stuck over the window's bottom as out of view, and scrolls to it (IR-477)", async () => {
    const scrollBy = vi.fn();
    vi.stubGlobal("scrollBy", scrollBy);
    vi.stubGlobal("innerHeight", 740);
    // The Review tab's action bar covers the bottom 112px of a 740px window.
    await openPaper(112);
    const input = await openFind();
    // Page 1's first line is at 600 + 100 = 700px: inside the window, under the bar.
    placePages([
      { top: 600, height: 1000 },
      { top: 1616, height: 1000 },
      { top: 2632, height: 1000 },
    ]);
    vi.spyOn(toolbar(), "getBoundingClientRect").mockReturnValue(box(READER_TOOLBAR_TOP_PX, 96));

    await userEvent.type(input, "vision");

    await waitFor(() =>
      expect(scrollBy).toHaveBeenCalledWith({ top: 700 - (READER_TOOLBAR_TOP_PX + 96) - 48, behavior: "auto" }),
    );
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

  /**
   * Review's Comment (IR-875): find is the keyboard's way to a passage, so
   * the current match is what Comment anchors to when nothing is selected.
   */
  describe("commenting on find's match", () => {
    function openCommentable(onComment: (passage: Passage, version: number) => void) {
      paperText = PAPER;
      render(
        <ReaderAnnotationsContext.Provider value={{ currentVersion: 2, marks: [], onComment, landing: null }}>
          <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />
        </ReaderAnnotationsContext.Provider>,
      );
      return screen.findByText("Page 1 / 3");
    }

    it("is offered only inside Review, and armed only by a passage", async () => {
      await openCommentable(vi.fn());
      const comment = screen.getByRole("button", { name: "Comment" });
      expect(comment).toBeDisabled();
      expect(comment).toHaveAttribute("aria-keyshortcuts", "C");
    });

    it("comments on the current match, by keyboard, on the Version shown", async () => {
      const onComment = vi.fn();
      await openCommentable(onComment);
      const input = await openFind();
      await userEvent.type(input, "robot arm");
      await waitFor(() => expect(screen.getByRole("button", { name: "Comment" })).toBeEnabled());
      await userEvent.keyboard("{Escape}");
      // Find closed: its match is gone, and so is the passage.
      await waitFor(() => expect(screen.getByRole("button", { name: "Comment" })).toBeDisabled());

      await userEvent.type(await openFind(), "robot arm");
      await waitFor(() => expect(screen.getByRole("button", { name: "Comment" })).toBeEnabled());
      screen.getByRole("button", { name: "Comment" }).focus();
      await userEvent.keyboard("{Enter}");
      expect(onComment).toHaveBeenCalledWith(expect.objectContaining({ page: 3, quote: "robot arm" }), 2);
    });
  });

});

/**
 * The selection menu and drawn highlights (IR-583, ADR-065). Find's current
 * match is the keyboard's way to a passage, as it is for Comment, so the tests
 * make one the way a keyboard reader would.
 */
describe("selected text actions (IR-583)", () => {
  const PAPER: TextRun[][] = [
    [line("Vision-language-action models", 0.1)],
    [line("Nothing to see here.", 0.2)],
    [line("A robot arm, and another ROBOT.", 0.5)],
  ];

  async function openWith(props: Partial<ComponentProps<typeof PaperPdfReader>> = {}) {
    paperText = PAPER;
    render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" {...props} />,
    );
    await screen.findByText("Page 1 / 3");
  }

  async function selectByFind(query = "robot arm") {
    await userEvent.click(screen.getByRole("button", { name: "Find in this paper" }));
    const input = await screen.findByRole("searchbox", { name: "Find in this paper" });
    await waitFor(() => expect(input).toHaveFocus());
    await userEvent.type(input, query);
  }

  const menu = () => screen.queryByRole("group", { name: "Selected text actions" });

  it("offers nothing when the page gave no actions", async () => {
    await openWith();
    await selectByFind();

    expect(menu()).not.toBeInTheDocument();
  });

  it("offers the actions it was given for a passage, and only while there is one", async () => {
    await openWith({ selectionActions: [{ id: "save-highlight", label: "Save highlight", icon: "fa-highlighter", run: vi.fn() }] });
    expect(menu()).not.toBeInTheDocument();

    await selectByFind();

    const group = await screen.findByRole("group", { name: "Selected text actions" });
    expect(within(group).getByRole("button", { name: "Save highlight" })).toBeInTheDocument();
  });

  it("runs an action with the passage and the Manuscript revision this paper was opened at", async () => {
    manuscriptBlob.mockResolvedValue({ data: pdfBlob(), headers: { "x-manuscript-revision": "rev-1" } });
    const run = vi.fn();
    await openWith({ selectionActions: [{ id: "save-highlight", label: "Save highlight", icon: "fa-highlighter", run }] });
    await selectByFind();

    await userEvent.click(await screen.findByRole("button", { name: "Save highlight" }));

    expect(run).toHaveBeenCalledTimes(1);
    expect(run).toHaveBeenCalledWith(expect.objectContaining({ page: 3, quote: "robot arm" }), "rev-1");
  });

  it("hands over no revision when the server named none", async () => {
    const run = vi.fn();
    await openWith({ selectionActions: [{ id: "save-highlight", label: "Save highlight", icon: "fa-highlighter", run }] });
    await selectByFind();

    await userEvent.click(await screen.findByRole("button", { name: "Save highlight" }));

    expect(run).toHaveBeenCalledWith(expect.anything(), null);
  });

  it("offers nothing on an earlier version: its bytes are not the paper a highlight belongs to", async () => {
    versionManuscriptBlob.mockResolvedValue({ data: pdfBlob() });
    await openWith({
      version: 2,
      selectionActions: [{ id: "save-highlight", label: "Save highlight", icon: "fa-highlighter", run: vi.fn() }],
    });
    await selectByFind();

    expect(menu()).not.toBeInTheDocument();
  });

  it("draws each saved highlight on its own page and no other", async () => {
    await openWith({
      highlights: [
        { key: 1, regions: [{ page: 3, left: 0.1, top: 0.5, right: 0.6, bottom: 0.55 }] },
        { key: 2, regions: [{ page: 1, left: 0.2, top: 0.1, right: 0.5, bottom: 0.12 }] },
      ],
    });

    const marks = (page: number) =>
      screen.getByRole("group", { name: `Page ${page}` }).querySelectorAll("[aria-hidden='true'] > span.reader-highlight");
    expect(marks(3)).toHaveLength(1);
    expect(marks(1)).toHaveLength(1);
    expect(marks(2)).toHaveLength(0);
    expect(parseFloat((marks(3)[0] as HTMLElement).style.left)).toBeCloseTo(10);
    expect(parseFloat((marks(3)[0] as HTMLElement).style.width)).toBeCloseTo(50);
  });

  it("has no serious or critical violations with the menu open", async () => {
    await openWith({ selectionActions: [{ id: "save-highlight", label: "Save highlight", icon: "fa-highlighter", run: vi.fn() }] });
    await selectByFind();
    await screen.findByRole("group", { name: "Selected text actions" });

    await expectNoBlockingA11yViolations(document.body);
  });
});

/**
 * A long manuscript (IR-565): a 100-page paper opens at its first or cited
 * page without waiting for the other 99, and only a bounded window of pages
 * around the view is ever painted.
 */
describe("a long manuscript (IR-565)", () => {
  /** A 100-page paper whose pages load only when `loads` says so. */
  function longPaper(loads: (n: number) => boolean = () => true) {
    const doc = fakeDocument(100);
    doc.getPage.mockImplementation((n: number) =>
      loads(n) ? Promise.resolve(fakePage(n)) : new Promise(() => {}),
    );
    loadPdfDocument.mockResolvedValue({ document: doc, destroy });
    return doc;
  }

  /** Whether a canvas render was started for `pageNumber`. */
  const painted = (pageNumber: number) =>
    renderPageToCanvas.mock.calls.some(([page]) => (page as { pageNumber: number }).pageNumber === pageNumber);

  it("shows the cited page before the rest of the paper has loaded", async () => {
    longPaper((n) => n === 60);
    render(<PaperPdfReader recordId={7} scrollToPage={60} highlightRegions={[]} navKey="a" />);

    expect(await screen.findByText("Page 1 / 100")).toBeInTheDocument();
    await waitFor(() => expect(painted(60)).toBe(true));
  });

  it("shows the first page before the rest of the paper has loaded, when nothing is cited", async () => {
    longPaper((n) => n === 1);
    render(<PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />);

    expect(await screen.findByText("Page 1 / 100")).toBeInTheDocument();
    await waitFor(() => expect(painted(1)).toBe(true));
  });

  it("waits for a newly cited page to paint before navigating to it", async () => {
    let finishPage: () => void = () => {};
    longPaper();
    const scrollBy = vi.fn();
    vi.stubGlobal("scrollBy", scrollBy);
    renderPageToCanvas.mockImplementation((page: { pageNumber: number }) => ({
      promise: page.pageNumber === 60 ? new Promise<void>((resolve) => { finishPage = resolve; }) : Promise.resolve(),
      cancel: vi.fn(),
    }));
    const { rerender } = render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await screen.findByText("Page 1 / 100");
    scrollBy.mockClear();

    rerender(<PaperPdfReader recordId={7} scrollToPage={60} highlightRegions={[]} navKey="b" />);
    await waitFor(() => expect(painted(60)).toBe(true));
    expect(scrollBy).not.toHaveBeenCalled();

    await act(async () => finishPage());
    await waitFor(() => expect(scrollBy).toHaveBeenCalled());
  });

  /**
   * The canvases the reader holds at once: a render started and not yet
   * cancelled is a page on a canvas. `peak` is the most there ever were.
   */
  function trackCanvases() {
    const live = new Map<number, number>();
    let peak = 0;
    renderPageToCanvas.mockImplementation((page: { pageNumber: number }) => {
      live.set(page.pageNumber, (live.get(page.pageNumber) ?? 0) + 1);
      peak = Math.max(peak, live.size);
      return {
        promise: Promise.resolve(),
        cancel: () => {
          const left = (live.get(page.pageNumber) ?? 1) - 1;
          if (left > 0) live.set(page.pageNumber, left);
          else live.delete(page.pageNumber);
        },
      };
    });
    return {
      pages: () => [...live.keys()].sort((a, b) => a - b),
      peak: () => peak,
    };
  }

  /** Gives all 100 pages a box: 1000px tall, 16px apart, `pageAtTop` at the window's top. */
  function placeAll(pageAtTop: number) {
    screen.getAllByRole("group", { name: /^Page \d+$/ }).forEach((page, i) => {
      const top = (i + 1 - pageAtTop) * 1016;
      vi.spyOn(page, "getBoundingClientRect").mockImplementation(() => box(top, 1000));
    });
  }

  /** As `placeAll`, then tells the reader the window scrolled. */
  function scrollTo(pageAtTop: number) {
    placeAll(pageAtTop);
    fireEvent.scroll(window);
  }

  /** Lets the reader's next-frame measurement run. */
  const nextFrames = () => act(() => new Promise((resolve) => setTimeout(resolve, 50)));

  it("paints only the pages around the view, not all 100", async () => {
    longPaper();
    const canvases = trackCanvases();
    render(<PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />);
    await screen.findByText("Page 1 / 100");

    // Every page has its box, so the paper scrolls its full length...
    await waitFor(() => expect(screen.getAllByRole("group", { name: /^Page \d+$/ })).toHaveLength(100));
    // ...but only the first page and the two after it are painted.
    await waitFor(() => expect(canvases.pages()).toEqual([1, 2, 3]));
    expect(canvases.peak()).toBeLessThanOrEqual(MAX_LIVE_PAGES);
  });

  it("moves the painted pages with the reader, dropping the ones left behind", async () => {
    longPaper();
    const canvases = trackCanvases();
    render(<PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />);
    await screen.findByText("Page 1 / 100");
    await waitFor(() => expect(screen.getAllByRole("group", { name: /^Page \d+$/ })).toHaveLength(100));

    scrollTo(50);

    expect(await screen.findByText("Page 50 / 100")).toBeInTheDocument();
    // Page 50 fills the 768px window; two pages either side are kept ready.
    await waitFor(() => expect(canvases.pages()).toEqual([48, 49, 50, 51, 52]));
    expect(canvases.peak()).toBeLessThanOrEqual(MAX_LIVE_PAGES);
  });

  it("finds text on a page far from the view, and paints that page before going there", async () => {
    longPaper();
    const canvases = trackCanvases();
    const scrollBy = vi.fn();
    vi.stubGlobal("scrollBy", scrollBy);
    paperText = Array.from({ length: 100 }, (_, i) => (i === 89 ? [line("The needle is here.", 0.5)] : []));
    render(<PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />);
    await screen.findByText("Page 1 / 100");

    await userEvent.click(screen.getByRole("button", { name: "Find in this paper" }));
    await userEvent.type(await screen.findByRole("searchbox", { name: "Find in this paper" }), "needle");

    await waitFor(() => expect(within(screen.getByRole("search")).getByRole("status")).toHaveTextContent("1 of 1"));
    const landing = scrollBy.mock.invocationCallOrder[scrollBy.mock.calls.findIndex(([arg]) => typeof arg === "object")];
    const paint = renderPageToCanvas.mock.invocationCallOrder[
      renderPageToCanvas.mock.calls.findIndex(([page]) => (page as { pageNumber: number }).pageNumber === 90)
    ];
    expect(landing).toBeDefined();
    expect(paint).toBeLessThan(landing);
    // The page's text layer is there to mark the match in.
    const page90 = screen.getByRole("group", { name: "Page 90" });
    expect(await within(page90).findByText("needle")).toBeInTheDocument();
    expect(canvases.peak()).toBeLessThanOrEqual(MAX_LIVE_PAGES);
  });

  it("does not pull the reader back as the rest of a paper of one page size loads", async () => {
    let releaseRest: () => void = () => {};
    const rest = new Promise<void>((resolve) => {
      releaseRest = resolve;
    });
    const doc = longPaper();
    doc.getPage.mockImplementation((n: number) =>
      n === 1 ? Promise.resolve(fakePage(n)) : rest.then(() => fakePage(n)),
    );
    const scrollBy = vi.fn();
    vi.stubGlobal("scrollBy", scrollBy);
    render(<PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />);
    await screen.findByText("Page 1 / 100");
    // The reader is measured at the top of page 1...
    scrollTo(1);
    await nextFrames();

    // ...then moved instantly, as a reduced-motion landing does, and the
    // other pages arrive before the next scroll is measured. Each is the size
    // it was estimated at, so nothing above the reader moved.
    placeAll(40);
    await act(async () => releaseRest());
    await nextFrames();

    expect(scrollBy.mock.calls.filter(([arg]) => typeof arg === "number")).toEqual([]);
  });

  it("forgets a find landing when find closes before its page has painted", async () => {
    longPaper();
    const scrollBy = vi.fn();
    vi.stubGlobal("scrollBy", scrollBy);
    let firstPaintOf90 = true;
    renderPageToCanvas.mockImplementation((page: { pageNumber: number }) => {
      const stalls = page.pageNumber === 90 && firstPaintOf90;
      if (stalls) firstPaintOf90 = false;
      return { promise: stalls ? new Promise<void>(() => {}) : Promise.resolve(), cancel: vi.fn() };
    });
    paperText = Array.from({ length: 100 }, (_, i) => (i === 89 ? [line("The needle is here.", 0.5)] : []));
    render(<PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />);
    await screen.findByText("Page 1 / 100");
    await userEvent.click(screen.getByRole("button", { name: "Find in this paper" }));
    await userEvent.type(await screen.findByRole("searchbox", { name: "Find in this paper" }), "needle");
    await waitFor(() => expect(within(screen.getByRole("search")).getByRole("status")).toHaveTextContent("1 of 1"));

    // Page 90 never finishes painting, so find has not moved the reader...
    await userEvent.keyboard("{Escape}");
    // ...and once find is closed, the reader scrolling there on their own
    // paints it without being jumped to the old match.
    scrollTo(89);
    await waitFor(() =>
      expect(renderPageToCanvas.mock.calls.filter(([page]) => (page as { pageNumber: number }).pageNumber === 90)).toHaveLength(2),
    );
    await nextFrames();

    expect(scrollBy.mock.calls.filter(([arg]) => typeof arg === "object")).toEqual([]);
  });
});

/**
 * Moving to another record or version (IR-565): what was loading for the old
 * one stops, and the document it opened is released exactly once.
 */
describe("leaving a paper for another", () => {
  it("discards the previous account's document and Find state when the session changes", async () => {
    const { unmount } = render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await screen.findByText("Page 1 / 3");
    await userEvent.click(screen.getByRole("button", { name: "Find in this paper" }));
    await userEvent.type(screen.getByRole("searchbox", { name: "Find in this paper" }), "old account");

    act(() => useAuthStore.setState((state) => ({ sessionEpoch: state.sessionEpoch + 1 })));

    await waitFor(() => expect(manuscriptBlob).toHaveBeenCalledTimes(2));
    expect(destroy).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("searchbox", { name: "Find in this paper" })).not.toBeInTheDocument();
    unmount();
  });

  it("aborts a fetch still in flight, and opens nothing for it", async () => {
    manuscriptBlob.mockImplementation(
      (_id: number, { signal }: { signal: AbortSignal }) =>
        new Promise((_, reject) => signal.addEventListener("abort", () => reject(new Error("aborted")))),
    );
    versionManuscriptBlob.mockResolvedValue({ data: pdfBlob() });
    const { rerender } = render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await waitFor(() => expect(manuscriptBlob).toHaveBeenCalledTimes(1));
    const { signal } = manuscriptBlob.mock.calls[0][1] as { signal: AbortSignal };

    rerender(<PaperPdfReader recordId={7} version={2} scrollToPage={null} highlightRegions={[]} navKey="a" />);

    expect(signal.aborted).toBe(true);
    expect(await screen.findByText("Page 1 / 3")).toBeInTheDocument();
    expect(versionManuscriptBlob).toHaveBeenCalledWith(7, 2, { signal: expect.any(AbortSignal) });
    expect(loadPdfDocument).toHaveBeenCalledTimes(1);
  });

  it("releases each version's document exactly once", async () => {
    const releaseCurrent = vi.fn(() => Promise.resolve());
    const releaseEarlier = vi.fn(() => Promise.resolve());
    loadPdfDocument
      .mockResolvedValueOnce({ document: fakeDocument(3), destroy: releaseCurrent })
      .mockResolvedValueOnce({ document: fakeDocument(5), destroy: releaseEarlier });
    versionManuscriptBlob.mockResolvedValue({ data: pdfBlob() });
    const { rerender, unmount } = render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await screen.findByText("Page 1 / 3");

    rerender(<PaperPdfReader recordId={7} version={2} scrollToPage={null} highlightRegions={[]} navKey="a" />);
    await screen.findByText("Page 1 / 5");
    expect(releaseCurrent).toHaveBeenCalledTimes(1);
    expect(releaseEarlier).not.toHaveBeenCalled();

    unmount();
    expect(releaseCurrent).toHaveBeenCalledTimes(1);
    expect(releaseEarlier).toHaveBeenCalledTimes(1);
  });

  it("releases a document that finished opening after the reader moved on, once", async () => {
    let open: (loaded: unknown) => void = () => {};
    loadPdfDocument.mockImplementation(
      () =>
        new Promise((resolve) => {
          open = resolve;
        }),
    );
    const { unmount } = render(
      <PaperPdfReader recordId={7} scrollToPage={null} highlightRegions={[]} navKey="a" />,
    );
    await waitFor(() => expect(loadPdfDocument).toHaveBeenCalledTimes(1));
    const [, signal] = loadPdfDocument.mock.calls[0] as [ArrayBuffer, AbortSignal];

    unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => open({ document: fakeDocument(3), destroy }));

    expect(destroy).toHaveBeenCalledTimes(1);
  });
});
