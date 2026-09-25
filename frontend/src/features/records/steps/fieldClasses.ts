/**
 * Class strings the wizard's hand-built controls share (IR-360), so a select
 * or textarea reads the same as `Input` beside it.
 */

/** A text control's box: stone at rest, maroon when invalid, as `Input` does it. */
export function fieldClasses(invalid: boolean): string {
  return `w-full border rounded-lg px-3 py-2 text-[13px] text-stone-900 outline-none transition-colors
    placeholder:text-stone-500 disabled:bg-stone-50 disabled:text-stone-500
    ${invalid
      // Maroon is also the focus colour, so an invalid field keeps its maroon
      // border and takes a heavier ring on focus (IR-359's Input).
      ? "border-brand focus:border-brand focus:ring-2 focus:ring-brand"
      : "border-stone-300 focus:border-brand focus:ring-1 focus:ring-brand"}`;
}

/** A field's label. */
export const LABEL = "block text-[13px] font-medium text-stone-700 mb-1";

/**
 * A checkbox in the palette. `accent-brand` colours the tick: with no
 * @tailwindcss/forms, `text-brand` alone leaves a checked box the browser's blue.
 */
export const CHECKBOX = "w-4 h-4 rounded border-stone-300 text-brand accent-brand focus:ring-brand";

/** The load-failure notice at the top of a step: maroon, with a glyph. */
export const LOAD_ERROR =
  "flex items-start gap-2 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-[13px] text-brand";
