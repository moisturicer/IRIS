import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { recordsApi } from "@/api/records";
import { Button, Skeleton } from "@/components/ui";
import { useElementWidth } from "@/hooks/useElementWidth";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cn, downloadBlob } from "@/lib/utils";
import { loadPdfDocument, pageSize, renderPageToCanvas, type PdfPage } from "@/lib/pdf";
import type { Region } from "@/types/ai";
import { CitationOverlay } from "./CitationOverlay";
import {
  CONTAINED_LAYOUT_QUERY,
  PANE_HEIGHT,
  PANE_TOP_PX,
  READER_TOOLBAR_TOP,
  READER_TOOLBAR_TOP_PX,
} from "./paneLayout";
import { MAX_SCALE, MIN_SCALE, citationLandingDelta, firstRegionOn, fitScale } from "./readerGeometry";
import { useReadingPosition } from "./useReadingPosition";

const SCALE_STEP = 0.2;
/** Used only until the pane has been measured, or where it cannot be. */
const DEFAULT_SCALE = 1.3;
/**
 * A window drag reports a new width every frame, and each refit repaints
 * every page. The first measurement applies at once, so the paper opens
 * fitted; later ones wait for the width to settle.
 */
const REFIT_DELAY_MS = 120;
/**
 * How long after a citation lands a refit still counts as the paper
 * settling rather than the reader acting (IR-354). The window's scrollbar
 * appears once the pages are in, the pane narrows, and the refit
 * `REFIT_DELAY_MS` later moves the passage and cancels the smooth scroll
 * on its way there; a refit this soon lands again. One much later -- the
 * reader dragging the window -- keeps their place instead.
 */
const SETTLE_AFTER_LANDING_MS = 1500;

/**
 * One rendered page: its own canvas, its own citation overlay, and a ref the
 * parent uses to scroll to it (IR-335).
 *
 * The box is sized from the page's own dimensions at the current zoom before
 * the canvas paints (IR-352), so a zoom change moves every page at once
 * instead of one by one as each render lands. That is also what lets the
 * reader restore its position in the same frame.
 */
function PdfPageView({
  page,
  pageNumber,
  scale,
  regions,
  registerRef,
}: {
  page: PdfPage;
  pageNumber: number;
  scale: number;
  regions: Region[];
  registerRef: (pageNumber: number, el: HTMLDivElement | null) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { width, height } = pageSize(page, scale);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rendering = renderPageToCanvas(page, canvas, scale);
    rendering.promise.catch(() => {
      /* a cancelled render rejects on purpose -- nothing to report */
    });
    return () => rendering.cancel();
  }, [page, scale]);

  return (
    <div
      ref={(el) => registerRef(pageNumber, el)}
      data-page-number={pageNumber}
      // A real accessible name, not only a data attribute this component's
      // own tests would otherwise have to reach for as a test id (CLAUDE.md:
      // queries go through the accessible tree). It also gives a screen
      // reader user landing on this region something to orient by, which a
      // bare `<canvas>` -- inherently opaque to assistive tech -- does not.
      role="group"
      aria-label={`Page ${pageNumber}`}
      className="relative mx-auto mb-4 last:mb-0 bg-white shadow-card ring-1 ring-stone-200"
      style={{ width, height }}
    >
      <canvas ref={canvasRef} className="block w-full h-full" />
      <CitationOverlay regions={regions.filter((r) => r.page === pageNumber)} />
    </div>
  );
}

export interface PaperPdfReaderProps {
  recordId: number;
  /** The page to scroll to once the document is ready, or `null` for none. */
  scrollToPage: number | null;
  /** Regions to highlight, already page-tagged -- filtered per page below. */
  highlightRegions: Region[];
  /**
   * Changes on every navigation that should re-scroll, even to the same
   * page — a second click on the same citation still means "look here." A
   * `location.key` from the caller is exactly that value.
   */
  navKey: string;
  /**
   * Rendered first in the toolbar: the Paper tab's way back to Ask IRIS
   * while the chat is closed (IR-372), so nothing floats over the paper.
   */
  toolbarStart?: ReactNode;
}

/**
 * The in-app PDF reader (IR-335) — what a citation opens into, in place of
 * the iframe/native-plugin viewer ADR-025 found could not be drawn on or
 * scrolled to programmatically.
 *
 * At `lg` and up it is a contained viewer (IR-352), like a document viewer's:
 * a pane as tall as the viewport below the header, whose pages scroll inside
 * it under a toolbar that never leaves. Below `lg` the page itself scrolls
 * and the toolbar sticks under the header (IR-351), because a scroll area
 * inside a scrolling page is awkward on touch. Either way the paper opens
 * fitted to the width it has.
 *
 * Fetched as a blob through `apiClient`, not a plain `<a href>`: the
 * manuscript endpoint requires `IsAuthenticated`, and only a request carrying
 * the bearer token in memory can reach it. The same blob backs the
 * download/open-in-new-tab affordance below with no second request.
 */
export function PaperPdfReader({
  recordId,
  scrollToPage,
  highlightRegions,
  navKey,
  toolbarStart,
}: PaperPdfReaderProps) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  const [pages, setPages] = useState<PdfPage[]>([]);
  const [zoom, setZoom] = useState<number | "fit">("fit");
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [downloadBytes, setDownloadBytes] = useState<Blob | null>(null);
  const pageRefs = useRef(new Map<number, HTMLDivElement>());
  const destroyRef = useRef<(() => Promise<void>) | null>(null);
  const paneRef = useRef<HTMLDivElement>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const contained = useMediaQuery(CONTAINED_LAYOUT_QUERY);
  // Read when a citation lands, not a reason to land again: the caller
  // builds a fresh `[]` on every render.
  const regionsRef = useRef(highlightRegions);
  regionsRef.current = highlightRegions;
  /** The last citation landed on: which navigation, at what zoom, and when. */
  const landedRef = useRef<{ navKey: string; scale: number; at: number } | null>(null);

  // The scroll area is both measured and scrolled. A callback ref, so the
  // one that replaces it after "Try again" is observed rather than the old.
  const scrollAreaRef = useRef<HTMLDivElement | null>(null);
  const [observeArea, paneWidth] = useElementWidth<HTMLDivElement>(REFIT_DELAY_MS);
  const scrollAreaCallbackRef = useCallback(
    (el: HTMLDivElement | null) => {
      scrollAreaRef.current = el;
      observeArea(el);
    },
    [observeArea],
  );

  // Fitted to the widest page, so a landscape table page never overflows.
  const baseWidth = useMemo(
    () => pages.reduce((widest, page) => Math.max(widest, pageSize(page, 1).width), 0),
    [pages],
  );
  const fitted = fitScale(baseWidth, paneWidth);
  const scale = zoom === "fit" ? (fitted ?? DEFAULT_SCALE) : zoom;

  const currentPage = useReadingPosition({
    ready: status === "ready",
    pageCount: pages.length,
    scale,
    pageRefs,
    toolbarRef,
    scrollAreaRef,
  });

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setPages([]);

    (async () => {
      try {
        const { data } = await recordsApi.manuscriptBlob(recordId);
        if (cancelled) return;
        const buffer = await data.arrayBuffer();
        const { document: doc, destroy } = await loadPdfDocument(buffer);
        if (cancelled) {
          void destroy();
          return;
        }
        destroyRef.current = destroy;

        const loaded: PdfPage[] = [];
        for (let n = 1; n <= doc.numPages; n += 1) {
          loaded.push(await doc.getPage(n));
        }
        if (cancelled) return;

        setPages(loaded);
        setDownloadBytes(data);
        setDownloadUrl(URL.createObjectURL(data));
        setStatus("ready");
      } catch {
        if (!cancelled) setStatus("error");
      }
    })();

    return () => {
      cancelled = true;
      void destroyRef.current?.();
      destroyRef.current = null;
    };
  }, [recordId, attempt]);

  useEffect(() => {
    return () => {
      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
    };
  }, [downloadUrl]);

  // Land a citation on its passage (IR-354): the first highlighted region
  // comes to rest just below the reader's toolbar, with a line or two above
  // it, rather than the page's top edge at the window's top -- under the
  // fixed header, and a lower passage off the screen altogether.
  useEffect(() => {
    if (status !== "ready" || scrollToPage == null) return;
    const landed = landedRef.current;
    const followed = landed?.navKey !== navKey;
    const settling =
      !followed &&
      landed !== null &&
      landed.scale !== scale &&
      performance.now() - landed.at < SETTLE_AFTER_LANDING_MS;
    if (!followed && !settling) return;
    const page = pageRefs.current.get(scrollToPage);
    const toolbar = toolbarRef.current;
    if (!page || !toolbar) return;
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const behavior: ScrollBehavior = reduceMotion ? "auto" : "smooth";
    const region = firstRegionOn(regionsRef.current, scrollToPage);
    const pageRect = page.getBoundingClientRect();
    const pageBox = { top: pageRect.top, height: pageRect.height };
    const toolbarRect = toolbar.getBoundingClientRect();
    const area = scrollAreaRef.current;

    if (contained && area && paneRef.current) {
      // The pane rests under the header and the view switch, and its pages
      // scroll under its own toolbar. Both are measured before either
      // scroll, and the window's scroll moves the toolbar and the page
      // alike, so neither changes the other's distance.
      const paneTop = paneRef.current.getBoundingClientRect().top;
      window.scrollBy({ top: paneTop - PANE_TOP_PX, behavior });
      const view = { top: toolbarRect.bottom, bottom: area.getBoundingClientRect().bottom };
      area.scrollBy({ top: citationLandingDelta(pageBox, region, view), behavior });
    } else {
      // The window scrolls, under a toolbar that sticks below the header.
      // Where it rests once stuck is what counts, not where it is now: a
      // reader at the top of the record has it well below that.
      const view = { top: READER_TOOLBAR_TOP_PX + toolbarRect.height, bottom: window.innerHeight };
      window.scrollBy({ top: citationLandingDelta(pageBox, region, view), behavior });
    }
    // The settling window runs from the landing itself, so a paper that
    // keeps refitting cannot keep pulling the reader back.
    landedRef.current = { navKey, scale, at: followed ? performance.now() : (landed?.at ?? 0) };
    // `navKey` is what makes clicking the same citation twice scroll (and
    // re-flash the highlight, via CitationOverlay's fresh element) a second
    // time. `scale` is for the settling refit above. `contained` is read,
    // not a trigger: crossing the breakpoint keeps the reader's place
    // (`useReadingPosition`), it does not land again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, scrollToPage, navKey, scale]);

  const registerRef = (pageNumber: number, el: HTMLDivElement | null) => {
    if (el) pageRefs.current.set(pageNumber, el);
    else pageRefs.current.delete(pageNumber);
  };

  const zoomIn = () => setZoom(Math.min(MAX_SCALE, +(scale + SCALE_STEP).toFixed(2)));
  const zoomOut = () => setZoom(Math.max(MIN_SCALE, +(scale - SCALE_STEP).toFixed(2)));

  const handleDownload = () => {
    if (downloadBytes) downloadBlob(downloadBytes, `record-${recordId}.pdf`);
  };

  if (status === "error") {
    return (
      <div className="flex flex-col items-center gap-3 py-16 px-6 text-center rounded-2xl border border-stone-200 bg-stone-50">
        <i className="fas fa-file-circle-exclamation text-2xl text-stone-300" aria-hidden />
        <p className="text-sm font-semibold text-stone-700">Could not load the paper</p>
        <p className="text-xs text-stone-500 max-w-sm">
          The file could not be read. Try again, or open it from Documents on the record.
        </p>
        <Button variant="outline" size="sm" onClick={() => setAttempt((n) => n + 1)}>
          <i className="fas fa-rotate-right" aria-hidden />
          Try again
        </Button>
      </div>
    );
  }

  const ready = status === "ready";

  return (
    <div
      ref={paneRef}
      className={cn(
        "flex flex-col",
        PANE_HEIGHT,
        "lg:rounded-2xl lg:border lg:border-stone-200 lg:bg-stone-100 lg:overflow-hidden",
      )}
    >
      <div
        ref={toolbarRef}
        className={cn(
          "sticky z-10 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 mb-3 px-2 py-1.5",
          "rounded-xl bg-white/90 backdrop-blur border border-stone-200",
          READER_TOOLBAR_TOP,
          "lg:static lg:shrink-0 lg:mb-0 lg:rounded-none lg:border-0 lg:border-b lg:bg-white lg:backdrop-blur-none",
        )}
      >
        <div className="flex items-center gap-1">
          {toolbarStart}
          <Button
            variant="ghost"
            size="icon"
            onClick={zoomOut}
            disabled={!ready || scale <= MIN_SCALE}
            aria-label="Zoom out"
          >
            <i className="fas fa-minus" aria-hidden />
          </Button>
          {/* The percentage gives way below `sm`, so the toolbar keeps its
              44px controls on one row at 360px. */}
          <span className="hidden sm:inline text-2xs font-semibold text-stone-500 w-10 text-center tabular-nums">
            {Math.round(scale * 100)}%
          </span>
          <Button
            variant="ghost"
            size="icon"
            onClick={zoomIn}
            disabled={!ready || scale >= MAX_SCALE}
            aria-label="Zoom in"
          >
            <i className="fas fa-plus" aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setZoom("fit")}
            disabled={!ready}
            aria-label="Fit to width"
            aria-pressed={zoom === "fit"}
            title="Fit to width"
          >
            <i className="fas fa-arrows-left-right-to-line" aria-hidden />
          </Button>
        </div>

        {ready && (
          <span className="text-xs font-semibold text-stone-600 tabular-nums">
            Page {currentPage} / {pages.length}
          </span>
        )}

        <Button
          variant="ghost"
          size="icon"
          onClick={handleDownload}
          disabled={!downloadBytes}
          aria-label="Download"
          title="Download the paper"
        >
          <i className="fas fa-download" aria-hidden />
        </Button>
      </div>

      {/* The pane's scroll area at `lg` and up; below it, just the pages.
          Focusable and named either way, so a keyboard user can page
          through it (axe: scrollable-region-focusable). */}
      <div
        ref={scrollAreaCallbackRef}
        role="region"
        aria-label={ready ? `Paper, ${pages.length} page${pages.length === 1 ? "" : "s"}` : "Paper"}
        tabIndex={0}
        className={cn(
          "rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",
          // A stable gutter, so the scrollbar appearing once the pages load
          // does not narrow the pane and set off a second refit.
          "lg:flex-1 lg:min-h-0 lg:overflow-y-auto lg:[scrollbar-gutter:stable] lg:rounded-none lg:p-4 lg:focus-visible:ring-inset",
        )}
      >
        {status === "loading" && (
          <div className="mx-auto max-w-2xl bg-white shadow-card ring-1 ring-stone-200">
            <Skeleton rows={8} label="Loading the paper…" />
          </div>
        )}

        {ready &&
          pages.map((page, index) => (
            <PdfPageView
              key={index + 1}
              page={page}
              pageNumber={index + 1}
              scale={scale}
              regions={highlightRegions}
              registerRef={registerRef}
            />
          ))}
      </div>
    </div>
  );
}
