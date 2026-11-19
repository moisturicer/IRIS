import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import { MAX_SCALE, MIN_SCALE } from "./readerGeometry";

/**
 * Zoom out, the percentage, zoom in and fit to width: the same four controls
 * in the PDF reader and the image reader (IR-1203), so a change to one is a
 * change to both.
 */
export function ZoomControls({
  scale,
  ready,
  fitting,
  onZoomOut,
  onZoomIn,
  onFit,
  compactPercent = false,
}: {
  scale: number;
  ready: boolean;
  fitting: boolean;
  onZoomOut: () => void;
  onZoomIn: () => void;
  onFit: () => void;
  /** The percentage gives way below `sm`, so a narrow toolbar keeps its 44px controls on one row at 360px. */
  compactPercent?: boolean;
}) {
  return (
    <>
      <Button variant="ghost" size="icon" onClick={onZoomOut} disabled={!ready || scale <= MIN_SCALE} aria-label="Zoom out">
        <i className="fas fa-minus" aria-hidden />
      </Button>
      <span className={cn("text-2xs font-semibold text-stone-600 w-10 text-center tabular-nums", compactPercent && "hidden sm:inline")}>
        {Math.round(scale * 100)}%
      </span>
      <Button variant="ghost" size="icon" onClick={onZoomIn} disabled={!ready || scale >= MAX_SCALE} aria-label="Zoom in">
        <i className="fas fa-plus" aria-hidden />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        onClick={onFit}
        disabled={!ready}
        aria-label="Fit to width"
        aria-pressed={fitting}
        title="Fit to width"
      >
        <i className="fas fa-arrows-left-right-to-line" aria-hidden />
      </Button>
    </>
  );
}

/** What a reader shows when it could not read its file, with the way to try again. */
export function ReaderLoadError({ title, hint, onRetry }: { title: string; hint: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 py-16 px-6 text-center rounded-card border border-stone-200 bg-stone-50">
      <i className="fas fa-file-circle-exclamation text-2xl text-stone-300" aria-hidden />
      <p className="text-sm font-semibold text-stone-700 break-words">{title}</p>
      <p className="text-xs text-stone-500">{hint}</p>
      <Button variant="outline" size="sm" onClick={onRetry}>
        <i className="fas fa-rotate-right" aria-hidden />
        Try again
      </Button>
    </div>
  );
}
