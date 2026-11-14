/**
 * The focus and motion rules of 01-design-system §0 (IR-405), as class
 * strings, so every new control states them the same way.
 */

/** A visible 2 px maroon ring with an offset, on keyboard focus only. */
export const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2";

/**
 * `FOCUS_RING` drawn on a link's stretched `::after`, so focus on the title of
 * a card that is one big link outlines the card (IR-1095).
 */
export const STRETCHED_FOCUS_RING =
  "focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-brand focus-visible:after:ring-offset-2";

/** A short colour change on hover or focus, and none under reduced motion. */
export const COLOUR_TRANSITION = "transition-colors duration-150 motion-reduce:transition-none";
