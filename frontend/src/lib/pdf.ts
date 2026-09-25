/**
 * The one place pdf.js is imported (IR-335).
 *
 * `PaperPdfReader` depends on this module, not on `pdfjs-dist` directly, so a
 * component test can mock the whole rendering pipeline — jsdom has no real
 * `<canvas>` 2D context and cannot run the pdf.js worker, so a test that
 * imported the library itself could not run at all.
 *
 * The worker is bundled by Vite (`?url` resolves to a hashed asset in the
 * build), never fetched from a CDN — a CDN dependency is one more thing that
 * can be down, and IRIS already renders a paper's own bytes locally.
 */
import * as pdfjsLib from "pdfjs-dist";
// Vite's `?url` suffix -- resolved at build time to a hashed asset URL, not
// a real module; `vite/client` provides the ambient type for it.
import pdfWorkerSrc from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerSrc;

export type PdfDocument = pdfjsLib.PDFDocumentProxy;
export type PdfPage = pdfjsLib.PDFPageProxy;

export interface LoadedPdf {
  document: PdfDocument;
  /**
   * Releases the document and its worker resources. Lives on the *loading
   * task* pdf.js returns, not on `PDFDocumentProxy` itself -- easy to reach
   * for wrong (`document.destroy` does not exist), which is exactly why this
   * wrapper hands the caller a bound function instead of the task.
   */
  destroy: () => Promise<void>;
}

export async function loadPdfDocument(data: ArrayBuffer): Promise<LoadedPdf> {
  const task = pdfjsLib.getDocument({ data });
  const document = await task.promise;
  return { document, destroy: () => task.destroy() };
}

/** A page's size in CSS pixels at a given zoom. */
export interface PageSize {
  width:  number;
  height: number;
}

/**
 * A page's pixel size at `scale`, without rendering it (IR-352).
 *
 * pdf.js computes a viewport synchronously, so the reader can size every
 * page's box the moment the zoom changes, before any canvas repaints. That
 * keeps the layout from jumping, and lets a reading position be restored in
 * the same frame. At scale 1 it is the page's size in PDF points.
 */
export function pageSize(page: PdfPage, scale: number): PageSize {
  const { width, height } = page.getViewport({ scale });
  return { width, height };
}

/**
 * Renders one page into `canvas` at `scale`.
 *
 * Drawn off-screen first and copied in once complete (IR-352): resizing a
 * canvas clears it, so rendering straight into the visible one blanked every
 * page for as long as a zoom change took to repaint them.
 *
 * Cancellable: `pdf.js`'s own `RenderTask.cancel()` is the documented way to
 * abandon a render that a scale change or an unmount has made moot, rather
 * than letting a stale render finish and paint over a newer one.
 */
export function renderPageToCanvas(
  page: PdfPage,
  canvas: HTMLCanvasElement,
  scale: number,
): { promise: Promise<void>; cancel: () => void } {
  const viewport = page.getViewport({ scale });
  const offscreen = document.createElement("canvas");
  offscreen.width = viewport.width;
  offscreen.height = viewport.height;

  const task = page.render({ canvas: offscreen, viewport });
  return {
    promise: task.promise.then(() => {
      canvas.width = offscreen.width;
      canvas.height = offscreen.height;
      canvas.getContext("2d")?.drawImage(offscreen, 0, 0);
    }),
    cancel: () => task.cancel(),
  };
}

/**
 * One run of a page's text as pdf.js extracted it (IR-353): what find
 * searches, and where on the page it sits.
 *
 * `top` and `bottom` are fractions of the page's height, like a citation's
 * `Region`, so a match lands through the same arithmetic a citation does
 * without the reader measuring the text layer. Runs are in the order the
 * text layer draws them, one span each, so a match's run index is also the
 * span it highlights.
 */
export interface TextRun {
  str: string;
  /** The run ends a line: find reads a space here, not two words joined. */
  eol: boolean;
  top: number;
  bottom: number;
}

/** A glyph's descent below its baseline, as a share of its height. */
const DESCENT = 0.2;

type TextContent = Awaited<ReturnType<PdfPage["getTextContent"]>>;
type ContentItem = TextContent["items"][number];
type TextItem = Extract<ContentItem, { str: string }>;

/**
 * The text content pdf.js extracts from `page`, fetched once and shared by
 * the text layer and find (IR-353), which would otherwise each ask the
 * worker for the same thing.
 */
const textContents = new WeakMap<PdfPage, Promise<TextContent>>();

function textContent(page: PdfPage): Promise<TextContent> {
  let content = textContents.get(page);
  if (!content) {
    content = page.getTextContent();
    textContents.set(page, content);
  }
  return content;
}

/** A text run, not a marked-content boundary -- the items the text layer draws a span for. */
function isTextItem(item: ContentItem): item is TextItem {
  return "str" in item;
}

/**
 * The page's text as runs (IR-353). A scanned page yields none, or only
 * whitespace, which is how the reader tells "no searchable text" from
 * "no matches".
 */
export async function pageText(page: PdfPage): Promise<TextRun[]> {
  const { items } = await textContent(page);
  const viewport = page.getViewport({ scale: 1 });
  return items.filter(isTextItem).map((item) => {
    const tx = pdfjsLib.Util.transform(viewport.transform, item.transform);
    const fontHeight = Math.hypot(tx[2], tx[3]);
    const baseline = tx[5];
    return {
      str: item.str,
      eol: item.hasEOL,
      top: clampFraction((baseline - fontHeight) / viewport.height),
      bottom: clampFraction((baseline + fontHeight * DESCENT) / viewport.height),
    };
  });
}

function clampFraction(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/** A page's text layer, drawn into a container over its canvas. */
export interface TextLayerHandle {
  /** Settles once every span is in the container. */
  promise: Promise<void>;
  /** Lays the spans out again for a new zoom. */
  update: (scale: number) => void;
  cancel: () => void;
  /** One span per `TextRun`, in the same order. */
  spans: () => HTMLElement[];
}

/**
 * Draws `page`'s text as transparent, positioned spans into `container`
 * (IR-353): what makes the paper's text selectable, and what find
 * highlights. pdf.js's own `TextLayer`, not its `PDFViewer`, which IRIS does
 * not use.
 *
 * The spans are placed in percentages of the page and sized from the
 * `--total-scale-factor` the page's box sets, so they follow a zoom with
 * no re-render; `update` only re-measures each span's width.
 */
export function renderTextLayer(page: PdfPage, container: HTMLElement, scale: number): TextLayerHandle {
  let layer: pdfjsLib.TextLayer | null = null;
  let cancelled = false;
  const promise = textContent(page).then((content) => {
    if (cancelled) return;
    layer = new pdfjsLib.TextLayer({
      textContentSource: content,
      container,
      viewport: page.getViewport({ scale }),
    });
    // pdf.js sizes the layer with CSS `round()`; the page's box already has
    // the right size, and the layer is `inset: 0` inside it.
    container.style.width = "100%";
    container.style.height = "100%";
    return layer.render();
  });
  return {
    promise: promise.then(() => undefined),
    update: (next) => layer?.update({ viewport: page.getViewport({ scale: next }) }),
    cancel: () => {
      cancelled = true;
      layer?.cancel();
    },
    spans: () => layer?.textDivs ?? [],
  };
}
