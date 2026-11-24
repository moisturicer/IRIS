import { useEffect, useState, type CSSProperties } from "react";

import { SlowLoadNotice, useLoadStage, usePlaceholderDelay } from "./slowLoad";

/**
 * The one loading placeholder (IR-158).
 *
 * Eleven screens each rendered their own `<div ...>Loading...</div>`. None of
 * them announced anything: a screen-reader user got silence while the table
 * loaded, then a table that had appeared without comment.
 *
 * The bars are `aria-hidden` -- they are decoration standing in for content that
 * is not there yet. What gets announced is `label`.
 */

/**
 * One pulsing placeholder shape (IR-1043). Every loading screen is built from
 * these, so a placeholder has one corner, one pulse and one reduced-motion
 * rule. `Skeleton` (rows of text) and `LoadingRegion` (a screen's own shape,
 * announced as loading) are the two ways to put them on a page; a screen never
 * draws its own `animate-pulse` box.
 *
 * `tone="soft"` (`stone-100`) is a body line or a card's content, `"strong"`
 * (`stone-200`) a heading or the one shape the eye lands on first. Size and
 * spacing come from `className`; the shape is decoration, so the caller hides
 * it (`LoadingRegion` does).
 */
const SHAPE = { control: "rounded-control", card: "rounded-card", pill: "rounded-full" } as const;

export function SkeletonBlock({ tone = "soft", shape = "control", className = "", style }: {
  tone?: "soft" | "strong";
  /** The corner of what it stands in for: a control or line, a card, or a pill or avatar. */
  shape?: "control" | "card" | "pill";
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      className={`${SHAPE[shape]} animate-pulse motion-reduce:animate-none ${tone === "strong" ? "bg-stone-200" : "bg-stone-100"} ${className}`}
      style={style}
    />
  );
}

interface SkeletonProps {
  /** Placeholder rows to draw. Defaults to 3. */
  rows?: number;
  /** Announced while loading. Defaults to "Loading…". */
  label?: string;
  /** Applied to the wrapper, e.g. to change the padding. */
  className?: string;
  /**
   * Reads again. Given, the loader offers Try again once it has gone on for
   * 10 s (IR-1078); a line saying it is still working appears after 2 s either way.
   */
  onRetry?: () => void;
}

export function Skeleton({ rows = 3, label = "Loading…", className = "", onRetry }: SkeletonProps) {
  // Every call site mounts this conditionally (`if (loading) return <Skeleton/>`),
  // so the live region arrives already carrying its text -- and a region that is
  // inserted already-populated is generally NOT announced by NVDA or JAWS; they
  // announce *changes* to a region they were already observing. Painting empty
  // first and filling in on the next tick gives them the mutation they listen
  // for. Without this the role="status" is decorative.
  const [announce, setAnnounce] = useState(false);
  useEffect(() => setAnnounce(true), []);
  const { stage, restart } = useLoadStage();
  // The bars, and the padding and size around them, wait 400 ms (IR-1314), so a
  // fast or empty answer never flashes lines of text it won't have.
  const showShapes = usePlaceholderDelay();

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={showShapes ? `p-8 ${className}` : undefined}
    >
      <span className="sr-only">{announce ? label : ""}</span>
      {showShapes ? (
        <div className="flex flex-col gap-3" aria-hidden="true">
          {Array.from({ length: rows }, (_, i) => (
            <SkeletonBlock
              key={i}
              tone="strong"
              className="h-4"
              // Ragged widths read as content rather than as a loading bar chart.
              style={{ width: `${100 - i * 8}%` }}
            />
          ))}
        </div>
      ) : (
        <div aria-hidden="true" />
      )}
      <SlowLoadNotice stage={stage} onRetry={onRetry} onRestart={restart} className="mt-4" />
    </div>
  );
}
