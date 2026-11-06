/**
 * How long an unbroken run of text may be before the parser sees it (IR-930).
 *
 * `remark-gfm`'s email autolink retries from every `+`, `-`, `.` and `_` inside
 * a run with no space, so its cost grows with the square of the run: measured
 * in Node, 40,000 characters of `x+x+x+...` took 3.5 s with it and 10 ms
 * without, all on the main thread while an answer renders. Answers are model
 * output built from manuscripts, so such a run can arrive. Breaking a long run
 * into pieces bounds the work of each attempt, and the total becomes linear:
 * the same input parses in ~100 ms.
 *
 * A "run" is a stretch of non-space characters, not a model token. 512 is above
 * any ordinary word, link or email address, so those are untouched. What a
 * break can still touch, in a run past the limit, all rare:
 * - a URL: the break lands inside its target, which then no longer resolves;
 * - a citation marker such as `[12]` that straddles a cut loses its chip;
 * - a code line or table delimiter row with no space is cut.
 * Formulas are not on this list: `remarkLimitMath` takes the breaks back out.
 * Copying text from a cut run carries the invisible break.
 */
export const MAX_RUN_CHARS = 512;

/** A zero-width space: invisible, offers the browser a place to wrap, and is
 *  not part of any email or URL, so the autolink scan stops at it. */
export const BREAK = String.fromCharCode(0x200b);

// A run is non-space, non-break text, so a run already cut by an earlier pass
// (or by a model that wrote its own break) is measured from its break.
const LONG_RUN = new RegExp(`[^\\s${BREAK}]{${MAX_RUN_CHARS + 1},}`, "gu");
const PIECE = new RegExp(`.{1,${MAX_RUN_CHARS}}`, "gsu");

/** `text` with a {@link BREAK} inside every run longer than {@link MAX_RUN_CHARS}. */
export function breakLongRuns(text: string): string {
  return text.replace(LONG_RUN, (run) => (run.match(PIECE) ?? [run]).join(BREAK));
}
