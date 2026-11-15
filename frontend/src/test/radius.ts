/**
 * What counts as an off-scale corner or shadow (IR-1043; 01-design-system.md
 * "Radius, shadow, spacing").
 *
 * There are three corner radii, named for what the shape is: `rounded-control`
 * (inputs, buttons that are not pills, chips and rows), `rounded-card` (cards
 * and panels) and `rounded-dialog` (modals and sheets). `rounded-full` is for
 * pills and avatars and `rounded-none` squares a corner off; both pass. A
 * corner utility (`rounded-t-`, `rounded-bl-`) takes the same names.
 *
 * Off the scale is Tailwind's own sizes (`rounded`, `-sm`, `-md`, `-lg`, `-xl`,
 * `-2xl`, `-3xl`, which `tailwind.config.js` no longer generates, so they would
 * render square and say nothing), any arbitrary `rounded-[..]`, and any
 * arbitrary `shadow-[..]`: shadow is kept for things that float, from the
 * named `shadow-card` and `shadow-card-md` (frontend_redesign_spec §4.12).
 */
const CORNER = "(?:-(?:t|b|l|r|tl|tr|bl|br|s|e|ss|se|es|ee))?";

/** Comments name the retired classes on purpose and say "rounded" as a word, so they are not scanned. */
export function withoutComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

const OFF_RADIUS = new RegExp(
  [
    // `rounded-lg`, `md:rounded-t-xl`: the default scale with a size.
    `(?<![\\w-])rounded${CORNER}-(?:sm|md|lg|xl|2xl|3xl)(?![\\w-])`,
    // `rounded-[3px]`, `before:rounded-bl-[14px]`.
    `(?<![\\w-])rounded${CORNER}-\\[[^\\]]*\\]`,
    // `rounded`, `rounded-t`: no size is the old DEFAULT.
    `(?<![\\w-])rounded${CORNER}(?![\\w-])`,
  ].join("|"),
  "g",
);

/** Every off-scale corner class in `source`, once each, in order of appearance. */
export function offRadiusClasses(source: string): string[] {
  const text = withoutComments(source);
  const found: string[] = [];
  for (const match of text.matchAll(OFF_RADIUS)) {
    const at = match.index ?? 0;
    // With no size the word could be a variable (`const rounded = ...`,
    // `Math.max(1, rounded)`), a property (`.rounded`) or prose. It is a class
    // only when a string or a stylesheet's `@apply` has it between separators.
    if (!/-(?:sm|md|lg|xl|2xl|3xl)$|\[/.test(match[0])) {
      const before = text[at - 1] ?? "";
      const after = text.slice(at + match[0].length);
      if (!/["'`\s]/.test(before) || !/^["'`\s;]/.test(after) || /^\s*[=,;)(.:?]/.test(after)) continue;
      if (/\b(?:const|let|var|return)\s+$/.test(text.slice(0, at))) continue;
    }
    found.push(match[0]);
  }
  return [...new Set(found)];
}

const ARBITRARY_SHADOW = /(?<![\w-])shadow-\[[^\]]*\]/g;

/** Every arbitrary `shadow-[..]` class in `source`, once each, in order of appearance. */
export function arbitraryShadowClasses(source: string): string[] {
  return [...new Set(withoutComments(source).match(ARBITRARY_SHADOW) ?? [])];
}
