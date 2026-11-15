import { useEffect, useRef, useState } from "react";

import { recordsApi } from "@/api/records";
import type { LoadedPdf } from "@/lib/pdf";

const RENDER_SCALE = 0.6;

interface PaperThumbnailProps {
  recordId: number;
  /** Whether the record has a manuscript to draw. Without one the outline stays. */
  available: boolean;
}

/**
 * The 96 px page beside a one-column result (IR-1082, D4; spec §4.6), showing the
 * paper's real first page (IR-1141). Until that is drawn, and wherever it can't
 * be (no manuscript, a failed read), the drawn page outline stands in, so a row
 * is the same size either way. The page is fetched only once the row nears the
 * viewport. Decoration only, so a screen reader skips it. Phones drop it, as the
 * prototype does, to give the title the width.
 */
export function PaperThumbnail({ recordId, available }: PaperThumbnailProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);
  const [drawn, setDrawn] = useState(false);

  useEffect(() => {
    if (!available || !hostRef.current) return;
    if (!("IntersectionObserver" in window)) {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: "300px" });
    observer.observe(hostRef.current);
    return () => observer.disconnect();
  }, [available]);

  useEffect(() => {
    if (!visible || !available) return;
    let cancelled = false;
    let loaded: LoadedPdf | null = null;
    let cancelRender: (() => void) | null = null;

    void (async () => {
      try {
        const { data } = await recordsApi.manuscriptBlob(recordId);
        if (cancelled) return;
        const { loadPdfDocument, renderPageToCanvas } = await import("@/lib/pdf");
        if (cancelled) return;
        loaded = await loadPdfDocument(await data.arrayBuffer());
        if (cancelled) return;
        const page = await loaded.document.getPage(1);
        const canvas = canvasRef.current;
        if (!canvas || cancelled) return;
        const rendered = renderPageToCanvas(page, canvas, RENDER_SCALE);
        cancelRender = rendered.cancel;
        await rendered.promise;
        if (!cancelled) setDrawn(true);
      } catch {
        // The outline stays.
      } finally {
        if (loaded) void loaded.destroy();
      }
    })();

    return () => {
      cancelled = true;
      cancelRender?.();
    };
  }, [available, recordId, visible]);

  return (
    <div
      ref={hostRef}
      aria-hidden="true"
      className="relative hidden aspect-[3/4] w-24 shrink-0 overflow-hidden rounded-control border border-stone-200 bg-surface shadow-card sm:block"
    >
      <div className="grid content-start gap-[5px] px-2 py-2.5">
        <span className="mx-auto mb-0.5 h-3.5 w-3.5 rounded-full border-2 border-stone-300" />
        <i className="mx-auto mb-1.5 mt-1 block h-[5px] w-4/5 rounded-full bg-stone-300" />
        {["w-full", "w-full", "w-3/5", "w-full", "w-full", "w-3/5"].map((width, index) => (
          <i key={index} className={`block h-[3px] rounded-full bg-stone-200 ${width}`} />
        ))}
      </div>
      {available && (
        <canvas
          ref={canvasRef}
          className={`absolute inset-0 h-full w-full bg-white object-cover object-top ${drawn ? "block" : "hidden"}`}
        />
      )}
    </div>
  );
}
