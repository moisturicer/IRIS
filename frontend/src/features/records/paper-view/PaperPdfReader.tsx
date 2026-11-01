import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Skeleton } from "@/components/ui";
import { useElementWidth } from "@/hooks/useElementWidth";
import { cn } from "@/lib/utils";
import {
  pageSize,
  renderPageToCanvas,
  renderTextLayer,
  type PdfPage,
  type TextLayerHandle,
} from "@/lib/pdf";
import type { Region } from "@/types/ai";
import { CitationOverlay } from "./CitationOverlay";
import { paintFindHits } from "./findHighlights";
import type { FindHit } from "./findInPaper";
import { PaperFind } from "./PaperFind";
import {
  PANE_TOP_PX,
  READER_TOOLBAR_TOP,
  READER_TOOLBAR_TOP_PX,
  READING_PANE_HEIGHT,
  READING_SPLIT_PX,
} from "./paneLayout";
import {
  MAX_SCALE,
  MIN_SCALE,
  citationLandingDelta,
  firstRegionOn,
  fitScale,
  liveWindow,
  regionInView,
  type RegionBand,
} from "./readerGeometry";
import { usePaperFind } from "./usePaperFind";
import { usePdfDocument } from "./usePdfDocument";
import { useReadingPosition } from "./useReadingPosition";
import { useAuthStore } from "@/store/auth.store";
import { SearchGlyph } from "@/components/brand/IrisBrand";

const SCALE_STEP = 0.2;
/**
 * The zoom a paper opens at (IR-569), and what an unmeasured pane uses. A
 * pane narrower than `READING_SPLIT_PX` -- a phone -- opens fitted instead,
 * since 140% would run well past its edge.
 */
const DEFAULT_SCALE = 1.4;
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

/** A page with no find hits: one value, so such pages never repaint. */
const NO_HITS: FindHit[] = [];

/**
 * A page's canvas and text layer (IR-353): mounted only while the page is in
 * the reader's live window (IR-565), so a long paper never holds more than
 * `MAX_LIVE_PAGES` of them. Leaving the window cancels a render still in
 * progress and drops both.
 *
 * The text layer is what makes the paper's text selectable and what find
 * highlights. It sits over the canvas and under the citation overlay, so a
 * citation's highlight still shows above a find's.
 */
function LivePageLayers({ page, scale, hits, onPaint }: {
  page: PdfPage; scale: number; hits: FindHit[];
  onPaint: (page: number, scale: number | null) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const layerRef = useRef<TextLayerHandle | null>(null);
  const [textReady, setTextReady] = useState(false);
  // The scale the text layer is first drawn at; later zooms `update` it.
  const scaleRef = useRef(scale);
  scaleRef.current = scale;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rendering = renderPageToCanvas(page, canvas, scale);
    let cancelled = false;
    rendering.promise.then(() => {
      if (!cancelled) onPaint(page.pageNumber, scale);
    }, () => {
      /* a cancelled render rejects on purpose -- nothing to report */
    });
    return () => { cancelled = true; rendering.cancel(); onPaint(page.pageNumber, null); };
  }, [page, scale, onPaint]);

  useEffect(() => {
    const container = textLayerRef.current;
    if (!container) return;
    const layer = renderTextLayer(page, container, scaleRef.current);
    layerRef.current = layer;
    layer.promise.then(
      () => setTextReady(true),
      () => {
        /* cancelled, or a page pdf.js could not read text from -- it stays unselectable */
      },
    );
    return () => {
      layer.cancel();
      layerRef.current = null;
      container.replaceChildren();
      setTextReady(false);
    };
  }, [page]);

  useEffect(() => {
    if (textReady) layerRef.current?.update(scale);
  }, [textReady, scale]);

  useEffect(() => {
    const layer = layerRef.current;
    if (textReady && layer) paintFindHits(layer.spans(), hits);
  }, [textReady, hits]);

  return (
    <>
      <canvas ref={canvasRef} className="block w-full h-full" />
      <div ref={textLayerRef} className="textLayer" />
    </>
  );
}

/**
 * One page of the paper: a box of the page's size at the current zoom, its
 * citation overlay, and a ref the parent uses to scroll to it (IR-335).
 *
 * The box is sized from the page's own dimensions before the canvas paints
 * (IR-352), so a zoom change moves every page at once instead of one by one
 * as each render lands. That is also what lets the reader restore its
 * position in the same frame.
 *
 * Outside the live window, or before pdf.js has loaded it, the box is all
 * there is (IR-565): the spacer that keeps the paper's scroll geometry. A
 * page not loaded yet is sized from `sizePage`, one that has; a paper's pages
 * are nearly always one size, and the reader keeps its place when one is not.
 */
function PdfPageView({
  page,
  sizePage,
  live,
  pageNumber,
  scale,
  regions,
  hits,
  registerRef,
  onPaint,
}: {
  page: PdfPage | undefined;
  sizePage: PdfPage;
  live: boolean;
  pageNumber: number;
  scale: number;
  regions: Region[];
  hits: FindHit[];
  registerRef: (pageNumber: number, el: HTMLDivElement | null) => void;
  onPaint: (page: number, scale: number | null) => void;
}) {
  const { width, height } = pageSize(page ?? sizePage, scale);

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
      // pdf.js sizes the text layer's glyphs from this (index.css, `.textLayer`).
      style={{ width, height, ["--total-scale-factor" as string]: scale }}
    >
      {live && page && <LivePageLayers page={page} scale={scale} hits={hits} onPaint={onPaint} />}
      <CitationOverlay regions={regions.filter((r) => r.page === pageNumber)} />
    </div>
  );
}

export interface PaperPdfReaderProps {
  recordId: number;
  /**
   * An earlier version to read instead of the current paper (IR-416), or
   * null/absent for the current one. Highlights and a citation's page belong
   * to the current paper, so the caller passes neither with a version.
   */
  version?: number | null;
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
   * The workspace is `reading-wide` (IR-569): the paper is a pane whose
   * pages scroll inside it, rather than with the window.
   */
  contained?: boolean;
  /**
   * Paper mode's workspace (IR-569): the pane fills a fixed-height column,
   * so it never moves and the window never scrolls to it.
   */
  fill?: boolean;
  /**
   * The toolbar's download control (IR-677): the caller's, because only the
   * record knows where the viewer's download stands. Absent, there is none --
   * the bytes this reader holds are never saved as a copy (ADR-048).
   */
  downloadControl?: ReactNode;
}

/**
 * The in-app PDF reader (IR-335) — what a citation opens into, in place of
 * the iframe/native-plugin viewer ADR-025 found could not be drawn on or
 * scrolled to programmatically.
 *
 * In a `reading-wide` workspace it is a contained viewer (IR-352, IR-569), like a document viewer's:
 * a pane as tall as the viewport below the header, whose pages scroll inside
 * it under a toolbar that never leaves. Narrower, the page itself scrolls
 * and the toolbar sticks under the header (IR-351), because a scroll area
 * inside a scrolling page is awkward on touch. Either way the paper opens
 * fitted to the width it has.
 *
 * A long paper opens at the useful page first (IR-565): the reader is ready
 * once the page it opens at has loaded (`usePdfDocument`), and only the pages
 * around the view -- plus one a citation or find is landing on -- carry a
 * canvas and a text layer (`liveWindow`). The rest are boxes of their size.
 *
 * Fetched as a blob through `apiClient`, not a plain `<a href>`: the
 * manuscript endpoint requires `IsAuthenticated`, and only a request carrying
 * the bearer token in memory can reach it. Saving a copy is not this blob:
 * it goes through the download route, which marks it (`downloadControl`).
 */
export function PaperPdfReader(props: PaperPdfReaderProps) {
  const epoch = useAuthStore((state) => state.sessionEpoch);
  return <PaperPdfReaderSource key={`${epoch}:${props.recordId}:${props.version ?? "current"}`} {...props} />;
}

function PaperPdfReaderSource({
  recordId,
  version = null,
  scrollToPage,
  highlightRegions,
  navKey,
  contained = false,
  fill = false,
  downloadControl,
}: PaperPdfReaderProps) {
  const [attempt, setAttempt] = useState(0);
  const { status, pageCount, pages, pageProxy, prioritize } = usePdfDocument({
    recordId,
    version,
    attempt,
    firstPage: scrollToPage,
  });
  const [zoom, setZoom] = useState<number | "fit" | null>(null);
  const [painted, setPainted] = useState<ReadonlyMap<number, number>>(new Map());
  const onPaint = useCallback((page: number, atScale: number | null) => {
    setPainted((previous) => {
      const next = new Map(previous);
      if (atScale === null) next.delete(page);
      else next.set(page, atScale);
      return next;
    });
  }, []);
  const [findLanding, setFindLanding] = useState<{ page: number; region: RegionBand } | null>(null);
  const pageRefs = useRef(new Map<number, HTMLDivElement>());
  const paneRef = useRef<HTMLDivElement>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
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

  // Fitted to the widest page loaded, so a landscape table page never overflows.
  const { baseWidth, sizePage, geometryKey } = useMemo(() => {
    const loaded = pages.filter((page): page is PdfPage => page !== undefined);
    const estimate = loaded[0] && pageSize(loaded[0], 1);
    // What the boxes' sizes rest on: the page unloaded ones are sized from,
    // and every loaded page that is not that size. A paper of one page size
    // keeps one key while the rest of it loads, so the reader's place is put
    // back only when a page above it really moved -- not on every chunk,
    // where a place measured before an instant landing would undo it.
    const resized = pages.flatMap((page, index) => {
      if (!page || !estimate) return [];
      const { width, height } = pageSize(page, 1);
      return width === estimate.width && height === estimate.height ? [] : [index + 1];
    });
    return {
      baseWidth: loaded.reduce((widest, page) => Math.max(widest, pageSize(page, 1).width), 0),
      sizePage: loaded[0],
      geometryKey: `${loaded[0]?.pageNumber ?? 0}|${resized.join(",")}`,
    };
  }, [pages]);
  const fitted = fitScale(baseWidth, paneWidth);
  const fitting = zoom === "fit" || (zoom === null && paneWidth > 0 && paneWidth < READING_SPLIT_PX);
  const scale = fitting ? (fitted ?? DEFAULT_SCALE) : (zoom ?? DEFAULT_SCALE);

  const { currentPage, lastVisiblePage } = useReadingPosition({
    ready: status === "ready",
    pageCount,
    scale,
    pageRefs,
    toolbarRef,
    scrollAreaRef,
    contained,
    geometryKey,
  });

  /**
   * Brings `region` of page `pageNumber` to rest just below the reader's
   * toolbar, with a line or two above it, or the page's top edge when there
   * is no region (IR-354). With `onlyIfHidden`, a region already in view
   * stays where it is, as a browser's find leaves a match the reader can
   * already see (IR-353). Returns whether there was a page to land on.
   */
  const land = (
    pageNumber: number,
    region: RegionBand | null,
    behavior: ScrollBehavior,
    onlyIfHidden = false,
  ): boolean => {
    const page = pageRefs.current.get(pageNumber);
    const toolbar = toolbarRef.current;
    if (!page || !toolbar) return false;
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
      const view = { top: toolbarRect.bottom, bottom: area.getBoundingClientRect().bottom };
      const atRest = fill || Math.abs(paneTop - PANE_TOP_PX) < 1;
      if (onlyIfHidden && region && atRest && regionInView(pageBox, region, view)) return true;
      if (!fill) window.scrollBy({ top: paneTop - PANE_TOP_PX, behavior });
      area.scrollBy({ top: citationLandingDelta(pageBox, region, view), behavior });
    } else {
      // The window scrolls, under a toolbar that sticks below the header.
      // Where it rests once stuck is what counts, not where it is now: a
      // reader at the top of the record has it well below that.
      const view = { top: READER_TOOLBAR_TOP_PX + toolbarRect.height, bottom: window.innerHeight };
      if (onlyIfHidden && region && regionInView(pageBox, region, view)) return true;
      window.scrollBy({ top: citationLandingDelta(pageBox, region, view), behavior });
    }
    return true;
  };

  // Land a citation on its passage (IR-354): the first highlighted region
  // comes to rest just below the reader's toolbar, with a line or two above
  // it, rather than the page's top edge at the window's top -- under the
  // fixed header, and a lower passage off the screen altogether.
  useEffect(() => {
    if (status !== "ready" || scrollToPage == null || painted.get(scrollToPage) !== scale) return;
    const landed = landedRef.current;
    const followed = landed?.navKey !== navKey;
    const settling =
      !followed &&
      landed !== null &&
      landed.scale !== scale &&
      performance.now() - landed.at < SETTLE_AFTER_LANDING_MS;
    if (!followed && !settling) return;
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const region = firstRegionOn(regionsRef.current, scrollToPage);
    if (!land(scrollToPage, region, reduceMotion ? "auto" : "smooth")) return;
    // The settling window runs from the landing itself, so a paper that
    // keeps refitting cannot keep pulling the reader back.
    landedRef.current = { navKey, scale, at: followed ? performance.now() : (landed?.at ?? 0) };
    // `navKey` is what makes clicking the same citation twice scroll (and
    // re-flash the highlight, via CitationOverlay's fresh element) a second
    // time. `scale` is for the settling refit above. `contained` is read,
    // not a trigger: crossing the breakpoint keeps the reader's place
    // (`useReadingPosition`), it does not land again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, scrollToPage, navKey, scale, painted]);

  const find = usePaperFind({
    ready: status === "ready",
    pageCount,
    pageProxy,
    currentPage,
    paneRef,
    // Instant, as a browser's find moves: a smooth scroll per keystroke
    // would still be travelling when the next one lands.
    land: (page, region) => setFindLanding({ page, region }),
  });

  // A landing still waiting for its page to paint is dropped with find: the
  // page is no longer pinned, and the reader scrolling to it later must not
  // be jumped to a match they closed.
  useEffect(() => {
    if (!find.open) setFindLanding(null);
  }, [find.open]);

  useEffect(() => {
    if (!findLanding || painted.get(findLanding.page) !== scale) return;
    land(findLanding.page, findLanding.region, "auto", true);
    setFindLanding(null);
    // Geometry is read only when the requested target has finished painting.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [findLanding, painted, scale]);

  // A citation's page and find's are painted before the reader is moved
  // there (`liveWindow`'s pins), and loaded out of turn if the background
  // loader has not reached them yet.
  const targetPage = find.targetPage;
  const live = useMemo(
    () => new Set(liveWindow(currentPage, lastVisiblePage, pageCount, [scrollToPage, targetPage])),
    [currentPage, lastVisiblePage, pageCount, scrollToPage, targetPage],
  );
  useEffect(() => {
    live.forEach(prioritize);
  }, [live, prioritize]);

  const registerRef = (pageNumber: number, el: HTMLDivElement | null) => {
    if (el) pageRefs.current.set(pageNumber, el);
    else pageRefs.current.delete(pageNumber);
  };

  const zoomIn = () => setZoom(Math.min(MAX_SCALE, +(scale + SCALE_STEP).toFixed(2)));
  const zoomOut = () => setZoom(Math.max(MIN_SCALE, +(scale - SCALE_STEP).toFixed(2)));

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
      onKeyDown={find.onReaderKeyDown}
      className={cn(
        "flex flex-col",
        fill
          ? "flex-1 min-h-0"
          : cn(
              READING_PANE_HEIGHT,
              "reading-wide:rounded-2xl reading-wide:border reading-wide:border-stone-200 reading-wide:overflow-hidden",
            ),
      )}
    >
      <div
        ref={toolbarRef}
        role="toolbar"
        aria-label="Paper tools"
        className={cn(
          fill
            ? "shrink-0 flex flex-wrap items-center gap-x-1 gap-y-1 min-h-12 px-2 reading-split:px-4 bg-stone-100 border-b border-stone-200"
            : cn(
                "sticky z-10 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 mb-3 px-2 py-1.5",
                "rounded-xl bg-overlay border border-stone-200",
                READER_TOOLBAR_TOP,
                "reading-wide:static reading-wide:shrink-0 reading-wide:mb-0 reading-wide:rounded-none",
                "reading-wide:border-0 reading-wide:border-b reading-wide:bg-canvas",
              ),
        )}
      >
        {fill && ready && (
          <span className="order-first px-2 text-small text-stone-600 tabular-nums">
            Page {currentPage} / {pageCount}
          </span>
        )}
        {fill && <span aria-hidden className="w-px h-5 bg-stone-300 mx-1" />}
        <div className="flex items-center gap-1">
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
          <span className={cn("text-2xs font-semibold text-stone-500 w-10 text-center tabular-nums", !fill && "hidden sm:inline")}>
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
            aria-pressed={fitting}
            title="Fit to width"
          >
            <i className="fas fa-arrows-left-right-to-line" aria-hidden />
          </Button>
          <Button
            ref={find.toggleRef}
            variant="ghost"
            size="icon"
            onClick={find.open ? find.closeFind : find.openFind}
            disabled={!ready}
            aria-label="Find in this paper"
            aria-expanded={find.open}
            title="Find in this paper (Ctrl+F)"
          >
            <SearchGlyph className="h-3.5 w-3.5" />
          </Button>
        </div>

        {!fill && ready && (
          <span className="text-xs font-semibold text-stone-600 tabular-nums">
            Page {currentPage} / {pageCount}
          </span>
        )}
        {fill && <span aria-hidden className="flex-1" />}

        {downloadControl}

        {/* A row of its own inside the toolbar, so it sticks with it and a
            match lands below both. */}
        {find.open && (
          <PaperFind
            ref={find.inputRef}
            query={find.query}
            status={find.status}
            onQueryChange={find.changeQuery}
            onNext={find.next}
            onPrevious={find.previous}
            onClose={find.closeFind}
          />
        )}
      </div>

      {/* The pane's scroll area when contained; otherwise just the pages.
          Focusable and named either way, so a keyboard user can page
          through it (axe: scrollable-region-focusable). */}
      <div
        ref={scrollAreaCallbackRef}
        role="region"
        aria-label={ready ? `Paper, ${pageCount} page${pageCount === 1 ? "" : "s"}` : "Paper"}
        tabIndex={0}
        className={cn(
          "rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",
          // A stable gutter, so the scrollbar appearing once the pages load
          // does not narrow the pane and set off a second refit.
          fill
            ? "flex-1 min-h-0 overflow-y-auto [scrollbar-gutter:stable] rounded-none bg-stone-200 px-3 py-4 reading-split:px-6 focus-visible:ring-inset"
            : cn(
                "reading-wide:flex-1 reading-wide:min-h-0 reading-wide:overflow-y-auto reading-wide:[scrollbar-gutter:stable]",
                "reading-wide:rounded-none reading-wide:p-4 reading-wide:focus-visible:ring-inset",
              ),
        )}
      >
        {status === "loading" && (
          <div className="mx-auto max-w-2xl bg-white shadow-card ring-1 ring-stone-200">
            <Skeleton rows={8} label="Loading the paper…" />
          </div>
        )}

        {ready &&
          sizePage &&
          pages.map((page, index) => (
            <PdfPageView
              key={index + 1}
              page={page}
              sizePage={sizePage}
              live={live.has(index + 1)}
              onPaint={onPaint}
              pageNumber={index + 1}
              scale={scale}
              regions={highlightRegions}
              hits={find.hitsByPage.get(index + 1) ?? NO_HITS}
              registerRef={registerRef}
            />
          ))}
      </div>
    </div>
  );
}
