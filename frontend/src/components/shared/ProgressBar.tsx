/**
 * A determinate progress bar (IR-471): the one bar `UploadDropzone`'s panel
 * and the Action-required banner's compact upload both draw, so the two cannot
 * drift apart in how they clamp, round, name or animate progress.
 *
 * The caller sizes it (`className` holds width, height and track colour) and
 * decides what sits beside it; the bar itself carries only the progressbar
 * semantics and the fill.
 */
import { forwardRef } from "react";

import { cn } from "@/lib/utils";

/** Progress as a whole percentage between 0 and 100, as the bar reports it. */
export function toPercent(progress: number): number {
  return Math.min(100, Math.max(0, Math.round(progress)));
}

interface ProgressBarProps {
  /** The bar's accessible name, e.g. "Uploading ethics.pdf". */
  label:     string;
  /** Any number; clamped to 0–100 and rounded. */
  progress:  number;
  /** Size and track colour, e.g. "h-1.5 w-20 bg-brand-100". */
  className?: string;
  /** Focusable from script only, for a caller that moves keyboard focus onto it. */
  focusable?: boolean;
}

export const ProgressBar = forwardRef<HTMLSpanElement, ProgressBarProps>(function ProgressBar(
  { label, progress, className, focusable = false },
  ref,
) {
  const percent = toPercent(progress);
  return (
    <span
      ref={ref}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      tabIndex={focusable ? -1 : undefined}
      className={cn("block rounded-full overflow-hidden", className)}
    >
      {/* Moved by transform, not width (01-design-system §0, motion). */}
      <span
        className="block h-full w-full origin-left rounded-full bg-brand transition-transform duration-200 motion-reduce:transition-none"
        style={{ transform: `scaleX(${percent / 100})` }}
      />
    </span>
  );
});
