/**
 * What counts as off-palette (IR-358; 01-design-system.md section 0).
 *
 * The interface is white, black, grey (`stone`) and maroon (`brand`). Off
 * palette is any colour-bearing Tailwind utility in a hue family outside that,
 * with or without variants (`hover:`, `md:`), opacity (`/80`) or `!`, plus
 * `brand-400` to `brand-600`, which are bright reds rather than maroon.
 *
 * `gray`/`slate` are greys and pass; they give way to `stone` as files are
 * touched, which is a review matter, not this guard's.
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
