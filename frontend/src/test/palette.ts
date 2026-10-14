/**
 * What counts as off-palette (IR-358; 01-design-system.md section 0).
 *
 * The interface is white, black, grey (`stone`) and maroon (`brand`). Off
 * palette is any colour-bearing Tailwind utility in a hue family outside that,
 * with or without variants (`hover:`, `md:`), opacity (`/80`) or `!`, plus
 * `brand-400` to `brand-600`, which are bright reds rather than maroon.
 *
 * Two more rules, added by IR-558 as an amendment to IR-358, which had let
 * `gray`/`slate` pass on purpose. They are checked separately from the hue
 * rule above, each with its own shrinking allowlist (palette.test.ts):
 *
 * - `gray` and `slate` are a second and third grey beside `stone`, which is
 *   the one grey (01-design-system.md section 0). Existing files may keep
 *   theirs until converted; a new one is rejected.
 * - A see-through white background (white at 60% opacity, say) shows whatever is behind
 *   it, so the same card reads as a different white on every screen. Content
 *   is `surface` and floating chrome is `overlay`, both opaque.
 */
const UTILITIES = [
  "bg", "text", "border", "border-[xytblrse]", "ring", "ring-offset", "outline",
  "divide", "fill", "stroke", "from", "via", "to", "placeholder", "decoration",
  "accent", "caret", "shadow",
].join("|");

const HUES = [
  "green", "emerald", "amber", "orange", "yellow", "red", "rose", "blue", "sky",
  "indigo", "violet", "purple", "teal", "cyan", "lime", "pink", "fuchsia",
].join("|");

const SHADE = "(?:50|[1-9]00|950)";

const OFF_PALETTE = new RegExp(
  `(?<![\\w-])(?:${UTILITIES})-(?:(?:${HUES})-${SHADE}|brand-[4-6]00)(?![\\w-])`,
  "g",
);

/** Every off-palette class in `source`, once each, in order of appearance. */
export function offPaletteClasses(source: string): string[] {
  return [...new Set(source.match(OFF_PALETTE) ?? [])];
}

const GREYS = ["gray", "slate"].join("|");

const OFF_GREY = new RegExp(
  `(?<![\\w-])(?:${UTILITIES})-(?:${GREYS})-${SHADE}(?![\\w-])`,
  "g",
);

/** Every `gray`/`slate` colour class in `source`, once each, in order of appearance. */
export function offGreyClasses(source: string): string[] {
  return [...new Set(source.match(OFF_GREY) ?? [])];
}

// White at any opacity below 100, in the `/60` or `/[0.6]` form; `/100` is opaque and passes.
const SEE_THROUGH_WHITE = /(?<![\w-])bg-white\/(?!100(?![\w-]))(?:\d{1,3}|\[[^\]]+\])(?![\w-])/g;

/** Every see-through white background in `source`, once each, in order of appearance. */
export function seeThroughWhiteClasses(source: string): string[] {
  return [...new Set(source.match(SEE_THROUGH_WHITE) ?? [])];
}
