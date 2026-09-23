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

/** A rendered page's own pixel size, so its container can be sized before the
 *  next layout pass rather than jumping once the canvas paints. */
export interface RenderedPageSize {
  width:  number;
  height: number;
}

/**
 * Renders one page into `canvas` at `scale` and returns its pixel size.
 *
 * Cancellable: `pdf.js`'s own `RenderTask.cancel()` is the documented way to
 * abandon a render that a scale change or an unmount has made moot, rather
 * than letting a stale render finish and paint over a newer one.
 */
export function renderPageToCanvas(
  page: PdfPage,
  canvas: HTMLCanvasElement,
  scale: number,
): { promise: Promise<RenderedPageSize>; cancel: () => void } {
  const viewport = page.getViewport({ scale });
  canvas.width = viewport.width;
  canvas.height = viewport.height;

  const task = page.render({ canvas, viewport });
  return {
    promise: task.promise.then(() => ({ width: viewport.width, height: viewport.height })),
    cancel: () => task.cancel(),
  };
}
