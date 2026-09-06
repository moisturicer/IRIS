import { useEffect, useState } from "react";

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

interface SkeletonProps {
  /** Placeholder rows to draw. Defaults to 3. */
  rows?: number;
  /** Announced while loading. Defaults to "Loading…". */
  label?: string;
  /** Applied to the wrapper, e.g. to change the padding. */
  className?: string;
}

export function Skeleton({ rows = 3, label = "Loading…", className = "" }: SkeletonProps) {
  // Every call site mounts this conditionally (`if (loading) return <Skeleton/>`),
  // so the live region arrives already carrying its text -- and a region that is
  // inserted already-populated is generally NOT announced by NVDA or JAWS; they
  // announce *changes* to a region they were already observing. Painting empty
  // first and filling in on the next tick gives them the mutation they listen
  // for. Without this the role="status" is decorative.
  const [announce, setAnnounce] = useState(false);
  useEffect(() => setAnnounce(true), []);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={`p-8 ${className}`}
    >
      <span className="sr-only">{announce ? label : ""}</span>
      <div className="flex flex-col gap-3" aria-hidden="true">
        {Array.from({ length: rows }, (_, i) => (
          <div
            key={i}
            className="h-4 rounded bg-gray-200 animate-pulse"
            // Ragged widths read as content rather than as a loading bar chart.
            style={{ width: `${100 - i * 8}%` }}
          />
        ))}
      </div>
    </div>
  );
}
