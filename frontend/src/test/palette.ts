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

/**
 * The retired highlight tints (IR-1097, D6; DESIGN.md "Decided changes").
 *
 * One pale pink, Maroon Wash (`brand-50`), once did about fifteen jobs: the
 * current page, a selected chip, the Active status, a citation, a search match,
 * a badge and a warning all looked alike. Each kind of highlight now has its
 * own look (`components/ui/highlightRoles.ts`), so the wash, the pinker
 * `brand-100` and the thread rose `brand-200` are not used as a fill, outline
 * or text colour anywhere, and neither is maroon at 5 or 10 percent, which is the
 * same pink made by opacity. Gold and cream went with them: the gold thumbnail
 * ring was off palette, and `cream` had one user.
 */
const RETIRED = [
  "brand-(?:50|100|200)",
  "brand/(?:5|10)",
  "gold(?:-(?:light|dark))?",
  "cream",
].join("|");

const RETIRED_TINT = new RegExp(
  `(?<![\\w-])(?:${UTILITIES})-(?:${RETIRED})(?![\\w-])`,
  "g",
);

/** Every retired wash, gold or cream colour class in `source`, once each, in order of appearance. */
export function retiredTintClasses(source: string): string[] {
  return [...new Set(source.match(RETIRED_TINT) ?? [])];
}

// The hexes the audit found loose in components, and the wash itself.
const STRAY_HEX = /#(?:fbe4e4|fcfcfb|5a0c0f|fdf2f2)(?![0-9a-f])/gi;

/** Every stray or retired hex in `source`, lower-cased, once each, in order of appearance. */
export function strayHexes(source: string): string[] {
  return [...new Set((source.match(STRAY_HEX) ?? []).map((h) => h.toLowerCase()))];
}

// White at any opacity below 100, in the `/60` or `/[0.6]` form; `/100` is opaque and passes.
const SEE_THROUGH_WHITE = /(?<![\w-])bg-white\/(?!100(?![\w-]))(?:\d{1,3}|\[[^\]]+\])(?![\w-])/g;

/** Every see-through white background in `source`, once each, in order of appearance. */
export function seeThroughWhiteClasses(source: string): string[] {
  return [...new Set(source.match(SEE_THROUGH_WHITE) ?? [])];
}
