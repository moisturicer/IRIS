import type { ReactNode } from "react";

import { SlowLoadNotice, useLoadStage } from "./slowLoad";

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
 */
export function LoadingRegion({ label, onRetry, className, children }: LoadingRegionProps) {
  const { stage, restart } = useLoadStage();
  return (
    <div role="status">
      <span className="sr-only">{label}</span>
      <div aria-hidden className={className}>{children}</div>
      <SlowLoadNotice stage={stage} onRetry={onRetry} onRestart={restart} className="mt-4" />
    </div>
  );
}
