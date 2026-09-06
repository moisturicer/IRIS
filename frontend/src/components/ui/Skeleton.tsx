/**
 * The one loading placeholder (IR-158).
 *
 * Ten screens each rendered their own `<div ...>Loading...</div>`. None of them
 * announced anything: a screen-reader user got silence while the table loaded,
 * then a table that had appeared without comment. `role="status"` on a live
 * region fixes that, and having one component means it stays fixed.
 *
 * The bars are `aria-hidden` -- they are decoration standing in for content that
 * is not there yet. What gets announced is `label`, once, via the `sr-only` text.
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
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={`p-8 ${className}`}
    >
      <span className="sr-only">{label}</span>
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
