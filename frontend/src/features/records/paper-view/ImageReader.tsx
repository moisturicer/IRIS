import { type ReactNode, useEffect, useState } from "react";
import { Button, Skeleton } from "@/components/ui";
import { useElementWidth } from "@/hooks/useElementWidth";
import { cn } from "@/lib/utils";
import { READING_PANE_HEIGHT } from "./paneLayout";
import { DOCUMENT_ROUTES, type ReaderDocument } from "./readerDocument";
import { fitScale, MAX_SCALE, MIN_SCALE } from "./readerGeometry";
import { ReaderWatermark } from "./ReaderWatermark";

const SCALE_STEP = 0.2;
/** The scroll area's own padding, both sides, kept clear of the fitted image. */
const FIT_GUTTER = 48;

type Loaded =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; url: string };

/**
 * A PNG or JPG supporting document in Review's reader (IR-1203), in the PDF
 * reader's frame: a toolbar with zoom, fit to width and the caller's download,
 * over a scroll area on stone, with the reader's watermark over the image
 * (IR-1128). There is no find, page count or selection: an image has no text.
 *
 * Its bytes come through the documents app's view route, so every read is
 * permission-checked and audited (IR-1200), and are let go when it closes.
 */
export function ImageReader({
  document: shown,
  fill = false,
  downloadControl,
}: {
  document: ReaderDocument;
  fill?: boolean;
  downloadControl?: ReactNode;
}) {
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null);
  const [zoom, setZoom] = useState<number | "fit">("fit");
  const [areaRef, areaWidth] = useElementWidth<HTMLDivElement>(120);

  useEffect(() => {
    const controller = new AbortController();
    let url: string | null = null;
    setLoaded({ status: "loading" });
    setNatural(null);
    DOCUMENT_ROUTES[shown.kind].view(shown.id, { signal: controller.signal })
      .then(({ data }) => {
        url = URL.createObjectURL(data);
        setLoaded({ status: "ready", url });
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoaded({ status: "error" });
      });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [shown.kind, shown.id, attempt]);

  // Fit to width never enlarges a small scan past its own size.
  const fitted = natural ? Math.min(1, fitScale(natural.width, areaWidth - FIT_GUTTER) ?? 1) : 1;
  const scale = zoom === "fit" ? fitted : zoom;
  const size = natural && { width: Math.round(natural.width * scale), height: Math.round(natural.height * scale) };
  const ready = loaded.status === "ready" && natural !== null;
  const fitting = zoom === "fit";
  const step = (by: number) => setZoom(Math.min(MAX_SCALE, Math.max(MIN_SCALE, +(scale + by).toFixed(2))));

  if (loaded.status === "error") {
    return (
      <div className="flex flex-col items-center gap-3 py-16 px-6 text-center rounded-card border border-stone-200 bg-stone-50">
        <i className="fas fa-file-circle-exclamation text-2xl text-stone-300" aria-hidden />
        <p className="text-sm font-semibold text-stone-700 break-words">Could not load {shown.label}</p>
        <p className="text-xs text-stone-500 max-w-sm">The file could not be read. Try again, or download it.</p>
        <Button variant="outline" size="sm" onClick={() => setAttempt((n) => n + 1)}>
          <i className="fas fa-rotate-right" aria-hidden />
          Try again
        </Button>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col",
        fill
          ? "flex-1 min-h-0"
          : cn(READING_PANE_HEIGHT, "reading-wide:rounded-card reading-wide:border reading-wide:border-stone-200 reading-wide:overflow-hidden"),
      )}
    >
      <div
        role="toolbar"
        aria-label="Image tools"
        className={cn(
          "shrink-0 flex flex-wrap items-center gap-x-1 gap-y-1 min-h-12 px-2 reading-split:px-4 bg-stone-100 border-b border-stone-200",
          !fill && "rounded-t-card border border-stone-200 reading-wide:rounded-none reading-wide:border-0 reading-wide:border-b",
        )}
      >
        <Button variant="ghost" size="icon" onClick={() => step(-SCALE_STEP)} disabled={!ready || scale <= MIN_SCALE} aria-label="Zoom out">
          <i className="fas fa-minus" aria-hidden />
        </Button>
        <span className="text-2xs font-semibold text-stone-600 w-10 text-center tabular-nums">{Math.round(scale * 100)}%</span>
        <Button variant="ghost" size="icon" onClick={() => step(SCALE_STEP)} disabled={!ready || scale >= MAX_SCALE} aria-label="Zoom in">
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
        <span aria-hidden className="flex-1" />
        {downloadControl}
      </div>

      {/* Focusable and named, so a keyboard user can scroll a zoomed image (axe: scrollable-region-focusable). */}
      <div
        ref={areaRef}
        role="region"
        aria-label={`Image, ${shown.label}`}
        tabIndex={0}
        className={cn(
          "overflow-auto [scrollbar-gutter:stable] bg-stone-200 p-6 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand/40",
          fill ? "flex-1 min-h-0" : "min-h-80 reading-wide:flex-1 reading-wide:min-h-0",
        )}
      >
        {loaded.status === "loading" && (
          <div className="mx-auto max-w-2xl bg-white shadow-card ring-1 ring-stone-200">
            <Skeleton rows={8} label={`Loading ${shown.label}…`} />
          </div>
        )}
        {loaded.status === "ready" && (
          <div
            className="relative mx-auto bg-white shadow-card ring-1 ring-stone-200"
            style={size ? { width: size.width, height: size.height } : { maxWidth: "100%" }}
          >
            <img
              src={loaded.url}
              alt={shown.label}
              draggable={false}
              onLoad={(e) => setNatural({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })}
              className="block h-full w-full"
            />
            {size && <ReaderWatermark width={size.width} height={size.height} scale={scale} />}
          </div>
        )}
      </div>
    </div>
  );
}
