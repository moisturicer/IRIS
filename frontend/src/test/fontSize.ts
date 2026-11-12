/**
 * What counts as an arbitrary font size, for the font-size guard (IR-1037).
 *
 * The type roles in `tailwind.config.js` (`text-display` ... `text-label`) are
 * the only way a screen should size text. A size written in square brackets,
 * `text-[` then a number and `px` or `rem`, bypasses them, and nothing used to
 * stop one being added.
 *
 * This file holds the scan and the advice; `fontSize.test.ts` holds the rule.
 * Both are excluded from the scan, because their examples are the thing it
 * rejects.
 */

export interface ArbitrarySize {
  /** The class as written, without any variant prefix: `text-[13px]`. */
  cls: string;
  /** The size in px; a `rem` size is multiplied by 16. */
  px: number;
}

/** The floor the spec sets for any text (frontend_redesign_spec section 4.12). */
export const MIN_TEXT_PX = 12;

// A variant prefix (`md:`) or an important marker (`!`) may precede the class,
// so the only thing ruled out in front of `text-` is a word or a hyphen, which
// would make it the tail of a longer name.
const ARBITRARY_SIZE = /(?<![\w-])text-\[(\d+(?:\.\d+)?)(px|rem)\]/g;

/** Every arbitrary font size in `source`, in the order written. */
export function arbitraryFontSizes(source: string): ArbitrarySize[] {
  return Array.from(source.matchAll(ARBITRARY_SIZE), ([cls, value, unit]) => ({
    cls,
    px: unit === "rem" ? Number(value) * 16 : Number(value),
  }));
}

/** True for a size under the 12 px floor. */
export function isBelowFloor(size: ArbitrarySize): boolean {
  return size.px < MIN_TEXT_PX;
}

/**
 * The type role nearest a pixel size, for the failure message. 14 px has no
 * role of its own: IR-1038 settles it as `text-body`.
 */
export function suggestedRole(px: number): string {
  if (px < MIN_TEXT_PX) return "text-label (12 px, the floor)";
  if (px <= 12) return "text-label";
  if (px <= 13) return "text-small";
  if (px <= 15) return "text-body";
  if (px <= 17) return "text-heading";
  if (px <= 24) return "text-title";
  return "text-display";
}
