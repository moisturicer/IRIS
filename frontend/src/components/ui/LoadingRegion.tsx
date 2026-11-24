import type { ReactNode } from "react";

import { SlowLoadNotice, useLoadStage, usePlaceholderDelay } from "./slowLoad";

interface LoadingRegionProps {
  /** Announced while loading: "Loading your research…". */
  label: string;
  /** Reads again. Given, Try again is offered once the wait passes 10 s (IR-1078). */
  onRetry?: () => void;
  /** Spacing and layout of the placeholder shapes. */
  className?: string;
  /** The placeholder shapes. They are decoration, so they are hidden from assistive technology. */
  children: ReactNode;
}

/**
 * A loading placeholder of a screen's own shape (the library's pulsing cards),
 * with what `Skeleton` gives the generic one: the label as a polite status, a
 * line of text after 2 s and Try again after 10 s.
 *
 * The shapes, and the room `className` gives them, appear only after 400 ms
 * (IR-1314): a fast answer, and above all an empty one, never shows the shape
 * of content it doesn't have. The label is in the region from the first frame.
 */
export function LoadingRegion({ label, onRetry, className, children }: LoadingRegionProps) {
  const { stage, restart } = useLoadStage();
  const showShapes = usePlaceholderDelay();
  return (
    <div role="status">
      <span className="sr-only">{label}</span>
      {showShapes ? <div aria-hidden className={className}>{children}</div> : <div aria-hidden />}
      <SlowLoadNotice stage={stage} onRetry={onRetry} onRestart={restart} className="mt-4" />
    </div>
  );
}
