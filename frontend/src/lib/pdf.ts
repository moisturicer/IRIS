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
