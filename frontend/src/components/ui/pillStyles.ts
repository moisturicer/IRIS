/**
 * Page-action pills (IR-356; 01-design-system.md section 0): 44px, rounded,
 * one filled primary per action row and the rest outlined.
 *
 * Class strings rather than a `Button` size, because two of the actions were
 * router `Link`s and one a dropdown trigger. `Button` has since become the same
 * pill (IR-1088: `size="page"`, and `ButtonLink` for a link), and the screens
 * that moved onto it no longer use these; the rest keep them until they do.
 */
import { SELECTED_RING } from "./highlightRoles";

const PILL =
  "inline-flex items-center justify-center gap-2 min-h-11 px-5 rounded-full text-sm font-semibold " +
  "transition-colors duration-200 disabled:opacity-60 disabled:cursor-not-allowed";

/** The one filled action in a row. */
export const PILL_PRIMARY = `${PILL} bg-brand text-white shadow-card hover:bg-brand-light active:bg-brand-press`;

/** Every other action. */
export const PILL_SECONDARY = `${PILL} bg-transparent text-stone-700 ring-1 ring-stone-300 hover:bg-stone-100 hover:text-stone-900`;

/** A toggle that is on (a paper saved to a collection). */
export const PILL_SELECTED = `${PILL} ${SELECTED_RING}`;
