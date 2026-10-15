import { useEffect, useRef, useState } from "react";

import { recordsApi } from "@/api/records";
import type { LoadedPdf } from "@/lib/pdf";

interface ManuscriptCoverProps {
  recordId: number;
  available: boolean;
}

export function ManuscriptCover({ recordId, available }: ManuscriptCoverProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">(
    available ? "loading" : "unavailable",
  );

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
        const rendered = renderPageToCanvas(page, canvas, 0.8);
        cancelRender = rendered.cancel;
        await rendered.promise;
        if (!cancelled) setStatus("ready");
      } catch {
        if (!cancelled) setStatus("unavailable");
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
    <div ref={hostRef} className="relative min-h-56 flex-1 overflow-hidden rounded-lg border border-stone-200 bg-stone-100 xl:rounded-none xl:rounded-tr-xl xl:border-0">
      {status !== "unavailable" && (
        <canvas
          ref={canvasRef}
          aria-label="First page of manuscript"
          role="img"
          className={`absolute inset-0 h-full w-full object-cover object-top ${status === "ready" ? "block" : "hidden"}`}
        />
      )}
      {status === "loading" && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 text-small text-stone-500">
          <i className="far fa-file-pdf text-lg" aria-hidden />
          Preparing first page…
        </div>
      )}
      {status === "unavailable" && (
        <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-small text-stone-600">
          <i className="far fa-file-pdf text-2xl text-stone-400" aria-hidden />
          <span>First page not available</span>
        </div>
      )}
      {status === "ready" && (
        <span className="absolute bottom-2 left-2 rounded bg-white/95 px-2 py-1 text-[11px] font-semibold text-stone-700 shadow-sm">
          First page
        </span>
      )}
    </div>
  );
}
