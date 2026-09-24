/**
 * Page-action pills (IR-356; 01-design-system.md section 0): 44px, rounded,
 * one filled primary per action row and the rest outlined.
 *
 * Class strings rather than a `Button` size, because two of the actions are
 * router `Link`s and one is a dropdown trigger, and the `Button` primitive's
 * base `rounded-lg` would fight `rounded-full` with no tailwind-merge to
 * settle it.
 */
const PILL =
  "inline-flex items-center justify-center gap-2 min-h-11 px-5 rounded-full text-sm font-semibold " +
  "transition-colors duration-200 disabled:opacity-60 disabled:cursor-not-allowed";

/** The one filled action in a row. */
export const PILL_PRIMARY = `${PILL} bg-brand text-white shadow-card hover:bg-brand-light`;

/** Every other action. */
export const PILL_SECONDARY = `${PILL} bg-white text-stone-700 ring-1 ring-stone-300 hover:ring-brand/40 hover:text-brand`;

/** A toggle that is on (a paper saved to a collection). */
export const PILL_SELECTED = `${PILL} bg-brand-50 text-brand ring-1 ring-brand-200`;
