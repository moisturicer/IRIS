/**
 * The font-size guard's allowance (IR-1037): how many arbitrary font sizes each
 * file may still contain. See `fontSize.test.ts` for the rule.
 *
 * It only shrinks. A file may use fewer than its allowance, and the test then
 * fails until the number is lowered here, so a cleaned file cannot slip back.
 * Remove a file's entry when it reaches zero. Adding a file or raising a number
 * needs a reason in the PR.
 */

/** Sizes of 12 px or more, by file. */
export const FONT_SIZE_ALLOWANCE: Record<string, number> = {
};

/**
 * Sizes under 12 px, by file: below the spec's floor, so kept apart. When this
 * is empty the floor holds everywhere and the test needs no exceptions.
 */
export const SUB_12PX_ALLOWANCE: Record<string, number> = {
};
