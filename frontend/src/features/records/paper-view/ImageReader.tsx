import { type ReactNode, useEffect, useState } from "react";
import { Skeleton } from "@/components/ui";
import { useElementWidth } from "@/hooks/useElementWidth";
import { READER_TOOLBAR_FILL } from "./paneLayout";
import { ReaderLoadError, ZoomControls } from "./ReaderControls";
import { DOCUMENT_ROUTES, type ReaderDocument } from "./readerDocument";
import { fitScale, MAX_SCALE, MIN_SCALE, SCALE_STEP } from "./readerGeometry";
import { ReaderWatermark } from "./ReaderWatermark";

/** The scroll area's own padding, both sides, kept clear of the fitted image. */
const FIT_GUTTER = 48;

type ReadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; url: string };

/**
 * A PNG or JPG supporting document in Review's reader (IR-1203), in the PDF
 * reader's frame where it fills the workspace's reading side: a toolbar with
 * zoom, fit to width and the caller's download, over a scroll area on stone,
 * with the reader's watermark over the image (IR-1128). There is no find,
 * page count or selection: an image has no text.
 *
 * Its bytes come through the documents app's view route, so every read is
 * permission-checked and audited (IR-1200). They are let go when it closes or
 * moves to another document, and a read it no longer needs makes none.
 */
export function ImageReader({
  document: shown,
  downloadControl,
}: {
  document: ReaderDocument;
  downloadControl?: ReactNode;
}) {
  const [read, setRead] = useState<ReadState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null);
  const [zoom, setZoom] = useState<number | "fit">("fit");
  const [areaRef, areaWidth] = useElementWidth<HTMLDivElement>(120);

  useEffect(() => {
    const controller = new AbortController();
    let url: string | null = null;
    setRead({ status: "loading" });
    setNatural(null);
    DOCUMENT_ROUTES[shown.kind].view(shown.id, { signal: controller.signal })
      .then(({ data }) => {
        if (controller.signal.aborted) return;
        url = URL.createObjectURL(data);
        setRead({ status: "ready", url });
      })
      .catch(() => {
        if (!controller.signal.aborted) setRead({ status: "error" });
      });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [shown.kind, shown.id, attempt]);

  // Each document starts fitted, whatever the last one was zoomed to.
  useEffect(() => setZoom("fit"), [shown.kind, shown.id]);

  // Fit to width never enlarges a small scan past its own size.
  const fitted = natural ? Math.min(1, fitScale(natural.width, areaWidth - FIT_GUTTER) ?? 1) : 1;
  const scale = zoom === "fit" ? fitted : zoom;
  const size = natural && { width: Math.round(natural.width * scale), height: Math.round(natural.height * scale) };
  const step = (by: number) => setZoom(Math.min(MAX_SCALE, Math.max(MIN_SCALE, +(scale + by).toFixed(2))));

  if (read.status === "error") {
    return (
      <ReaderLoadError
        title={`Could not load ${shown.label}`}
        hint="The file could not be read. Try again, or download it."
        onRetry={() => setAttempt((n) => n + 1)}
      />
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div role="toolbar" aria-label="Image tools" className={READER_TOOLBAR_FILL}>
        <ZoomControls
          scale={scale}
          ready={read.status === "ready" && natural !== null}
          fitting={zoom === "fit"}
          onZoomOut={() => step(-SCALE_STEP)}
          onZoomIn={() => step(SCALE_STEP)}
          onFit={() => setZoom("fit")}
        />
        <span aria-hidden className="flex-1" />
        {downloadControl}
      </div>

      {/* Focusable and named, so a keyboard user can scroll a zoomed image (axe: scrollable-region-focusable). */}
      <div
        ref={areaRef}
        role="region"
        aria-label={`Image, ${shown.label}`}
        tabIndex={0}
        className="flex-1 min-h-0 overflow-auto [scrollbar-gutter:stable] bg-stone-200 p-6 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand/40"
      >
        {read.status === "loading" && (
          <div className="mx-auto max-w-2xl bg-white shadow-card ring-1 ring-stone-200">
            <Skeleton rows={8} label={`Loading ${shown.label}…`} />
          </div>
        )}
        {read.status === "ready" && (
          <div
            className="relative mx-auto bg-white shadow-card ring-1 ring-stone-200"
            style={size ? { width: size.width, height: size.height } : { maxWidth: "100%" }}
          >
            <img
              src={read.url}
              alt={shown.label}
              draggable={false}
              onLoad={(e) => setNatural({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })}
              // Bytes that arrived but are no image the browser can draw, such as a
              // file named .png before IR-1220 checked first bytes.
              onError={() => setRead({ status: "error" })}
              className="block h-full w-full"
            />
            {size && <ReaderWatermark width={size.width} height={size.height} scale={scale} />}
          </div>
        )}
      </div>
    </div>
  );
}
