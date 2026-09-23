import { useEffect, useRef, useState } from "react";
import { recordsApi } from "@/api/records";
import { downloadBlob } from "@/lib/utils";
import { loadPdfDocument, renderPageToCanvas, type PdfPage } from "@/lib/pdf";
import type { Region } from "@/types/ai";
import { CitationOverlay } from "./CitationOverlay";

const MIN_SCALE = 0.6;
const MAX_SCALE = 2.4;
const SCALE_STEP = 0.2;
const DEFAULT_SCALE = 1.3;

/**
 * One rendered page: its own canvas, its own citation overlay, and a ref the
 * parent uses to scroll to it (IR-335).
 *
 * A page renders itself independently rather than the reader rendering all
 * pages in one pass, so a scale change or a re-mount cancels and restarts
 * only the pages actually visible to re-render, not the whole document.
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
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rendering = renderPageToCanvas(page, canvas, scale);
    rendering.promise.then(setSize).catch(() => {
      /* a cancelled render rejects on purpose -- nothing to report */
    });
    return () => rendering.cancel();
  }, [page, scale]);

  return (
    <div
      ref={(el) => registerRef(pageNumber, el)}
      data-page-number={pageNumber}
      className="relative mx-auto mb-4 bg-white shadow-card border border-stone-200"
      style={size ? { width: size.width, height: size.height } : { minHeight: 400 }}
    >
      <canvas ref={canvasRef} className="block" />
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
}

/**
 * The in-app PDF reader (IR-335) — what a citation opens into, in place of
 * the iframe/native-plugin viewer ADR-025 found could not be drawn on or
 * scrolled to programmatically.
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
}: PaperPdfReaderProps) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [pages, setPages] = useState<PdfPage[]>([]);
  const [scale, setScale] = useState(DEFAULT_SCALE);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [downloadBytes, setDownloadBytes] = useState<Blob | null>(null);
  const pageRefs = useRef(new Map<number, HTMLDivElement>());
  const destroyRef = useRef<(() => Promise<void>) | null>(null);

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
  }, [recordId]);

  useEffect(() => {
    return () => {
      if (downloadUrl) URL.revokeObjectURL(downloadUrl);
    };
  }, [downloadUrl]);

  useEffect(() => {
    if (status !== "ready" || scrollToPage == null) return;
    const target = pageRefs.current.get(scrollToPage);
    target?.scrollIntoView({ block: "start", behavior: "smooth" });
    // `navKey` deliberately in the dependency list with no other use: it is
    // what makes clicking the same citation twice scroll (and re-flash the
    // highlight, via CitationOverlay's fresh element) a second time.
  }, [status, scrollToPage, navKey]);

  const registerRef = (pageNumber: number, el: HTMLDivElement | null) => {
    if (el) pageRefs.current.set(pageNumber, el);
    else pageRefs.current.delete(pageNumber);
  };

  const zoomIn = () => setScale((s) => Math.min(MAX_SCALE, +(s + SCALE_STEP).toFixed(2)));
  const zoomOut = () => setScale((s) => Math.max(MIN_SCALE, +(s - SCALE_STEP).toFixed(2)));

  const handleDownload = () => {
    if (downloadBytes) downloadBlob(downloadBytes, `record-${recordId}.pdf`);
  };

  if (status === "error") {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <i className="fas fa-file-circle-exclamation text-[28px] text-stone-300" aria-hidden />
        <p className="text-[13px] font-semibold text-stone-700">Could not load the paper</p>
        <p className="text-[12px] text-stone-500">
          The file could not be read. Try again, or use Documents in the sidebar.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="sticky top-0 z-10 flex items-center justify-between gap-3 mb-3 px-3 py-2 rounded-xl bg-white/90 backdrop-blur border border-stone-200">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={zoomOut}
            disabled={status !== "ready" || scale <= MIN_SCALE}
            aria-label="Zoom out"
            className="w-7 h-7 rounded-md border border-stone-200 text-stone-600 hover:border-brand/40 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center"
          >
            <i className="fas fa-minus text-[10px]" aria-hidden />
          </button>
          <span className="text-[11px] font-semibold text-stone-500 w-10 text-center tabular-nums">
            {Math.round(scale * 100)}%
          </span>
          <button
            type="button"
            onClick={zoomIn}
            disabled={status !== "ready" || scale >= MAX_SCALE}
            aria-label="Zoom in"
            className="w-7 h-7 rounded-md border border-stone-200 text-stone-600 hover:border-brand/40 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center"
          >
            <i className="fas fa-plus text-[10px]" aria-hidden />
          </button>
        </div>

        {status === "ready" && (
          <span className="text-[11px] text-stone-400">{pages.length} page{pages.length === 1 ? "" : "s"}</span>
        )}

        <button
          type="button"
          onClick={handleDownload}
          disabled={!downloadBytes}
          className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-stone-600 hover:text-brand disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <i className="fas fa-download text-[10px]" aria-hidden />
          Download
        </button>
      </div>

      {status === "loading" && (
        <div className="flex flex-col items-center gap-3 py-16">
          <i className="fas fa-circle-notch fa-spin text-[24px] text-stone-300" aria-hidden />
          <p className="text-[12px] text-stone-400">Loading the paper…</p>
        </div>
      )}

      {status === "ready" && (
        <div>
          {pages.map((page, index) => (
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
      )}
    </div>
  );
}
