/**
 * One look per kind of highlight (IR-1097, D6; DESIGN.md "Decided changes";
 * `iris-uiux-audit/design-system.md` section 1).
 *
 * One pale pink, Maroon Wash, once did about fifteen jobs: the current page, a
 * selected chip, the Active status, a citation, a search match, a badge and a
 * warning all looked alike. Each job has its own look now, and no look means
 * two things. A screen asks for the role and never picks a tint by hand:
 *
 * | Role      | Look                                                    | Where it lives            |
 * |-----------|---------------------------------------------------------|---------------------------|
 * | Action    | Maroon fill, one per row                                | `PILL_PRIMARY`, `Button`  |
 * | Here      | Desk Stone fill, Ink text, maroon icon, no side stripe  | `HERE`                    |
 * | Selected  | White with an Ink outline, never maroon                 | `SELECTED`, `SELECTED_RING`, `SELECTED_SEGMENT` |
 * | Reference | Maroon text on white, Rule Stone hairline               | `REFERENCE`               |
 * | Match     | Yellow highlighter `hl`; the current Find match `hl-now`| `MATCH`; `index.css` for the PDF |
 * | Pen       | Rose fill `pen-wash`, 2 px `pen` underline, numbered pin; the open thread `pen-now` | `index.css`, `readerAnnotations.tsx` |
 * | Status    | White chip, tone in text and outline; only Attention is filled | `statusTones.ts`   |
 *
 * Yellow is for matches only and rose for a reviewer's marks only. A message
 * that needs reading (a warning, an error) is white with a Rule Stone outline
 * and maroon text beside an icon and a word, so it never reads as a selection
 * or a match. `test/palette.test.ts` keeps the retired tints (`brand-50`,
 * `brand-100`, `brand-200`) out of the source.
 */

/**
 * Where you are: the current page, tab or conversation, or a comment you jumped
 * to. The icon beside it is maroon. No coloured stripe: a stripe on a list item
 * is decoration, and the fill already says where you are.
 */
export const HERE = "bg-stone-200 font-semibold text-stone-900";

/**
 * An option you chose, drawn with a border: a filter that is on, a chosen
 * record type, an option card. Never maroon. Ink-outlined on white, so it reads
 * apart from `HERE` (a fill). A `settled` status is also an Ink outline, which
 * the design system allows because a status always carries its word and icon.
 */
export const SELECTED = "border-stone-900 bg-surface text-stone-900 ring-1 ring-stone-900";

/** `SELECTED` for a control drawn with a ring and no border (a pill, a chip). */
export const SELECTED_RING = "bg-surface text-stone-900 ring-2 ring-stone-900";

/**
 * A segment of a segmented control that is chosen: white and raised on the
 * stone track, with a Rule Stone hairline. The unchosen segments sit flat.
 */
export const SELECTED_SEGMENT = "bg-surface text-stone-900 shadow-card ring-1 ring-stone-300";

/**
 * IRIS pointing at a source: a page citation or a source number. Maroon text on
 * white with a Rule Stone hairline, and a maroon fill on hover.
 */
export const REFERENCE =
  "bg-surface text-brand ring-1 ring-stone-300 transition-colors duration-150 " +
  "hover:bg-brand hover:text-white hover:ring-brand motion-reduce:transition-none";

/** A word a search matched: the one yellow, with Ink on it (14:1). */
export const MATCH = "bg-hl text-stone-900";
