/**
 * Class strings hand-built form controls share (IR-360), so a select
 * or textarea reads the same as `Input` beside it.
 */

/** A text control's box: stone at rest, maroon when invalid, as `Input` does it. */
export function fieldClasses(invalid: boolean): string {
  return `w-full border rounded-lg px-3 py-2 text-body text-stone-900 outline-none transition-colors
    placeholder:text-stone-500 disabled:bg-stone-50 disabled:text-stone-500
    ${invalid
      // Maroon is also the focus colour, so an invalid field keeps its maroon
      // border and takes a heavier ring on focus (IR-359's Input).
      ? "border-brand focus:border-brand focus:ring-2 focus:ring-brand"
      : "border-stone-300 focus:border-brand focus:ring-1 focus:ring-brand"}`;
}

/** A field's label. */
export const LABEL = "block text-body font-medium text-stone-700 mb-1";

/**
 * A checkbox in the palette. `accent-brand` colours the tick: with no
 * @tailwindcss/forms, `text-brand` alone leaves a checked box the browser's blue.
 */
export const CHECKBOX = "w-4 h-4 rounded border-stone-300 text-brand accent-brand focus:ring-brand";

/** A warning notice: maroon, with a glyph supplied by the caller. */
export const WARNING_NOTICE =
  "flex items-start gap-2 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-body text-brand";

/** Load failures use the same attention tone as warnings. */
export const LOAD_ERROR = WARNING_NOTICE;
