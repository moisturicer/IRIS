/**
 * The Paper View's sticky and pane geometry (IR-351, IR-352, IR-356).
 *
 * Top to bottom: nothing -- there is no app header since IR-519 -- then 8px
 * down the floating section switch, 48px tall; 12px below that the panes --
 * the reader, the docked Paper Chat and the rail -- which share one height so
 * their tops and bottoms line up, ending at the page's 28px bottom padding.
 * Below `md` a phone bar sits above the page, but it scrolls away rather than
 * sticking, so nothing here is measured from it.
 *
 * Whole class strings, because Tailwind only generates classes it finds
 * written out in source. There are no spacing tokens for these offsets; they
 * live here once. Change the switch or the `icon` Button's 44px, and these
 * change with it. `paneLayout.test.ts` pins the arithmetic.
 */

/** Where the reader becomes a contained pane: Tailwind's `lg`, 1024px. */
export const CONTAINED_LAYOUT_QUERY = "(min-width: 1024px)";

/** The floating view switch: 8px from the top of the window. */
export const VIEW_SWITCH_TOP = "top-[8px]";

/** Panes: 12px below the switch (8 + 48 + 12). */
export const PANE_TOP = "lg:top-[68px]";

/** `PANE_TOP` as a number, for the reader to scroll its pane to (IR-354). */
export const PANE_TOP_PX = 68;

/** The viewport less everything above a pane and the 28px bottom padding. */
export const PANE_HEIGHT = "lg:h-[calc(100vh-96px)]";
export const PANE_MAX_HEIGHT = "lg:max-h-[calc(100vh-96px)]";

/** Below `lg` the reader's toolbar sticks 8px under the switch instead (8 + 48 + 8). */
export const READER_TOOLBAR_TOP = "top-[64px]";

/**
 * `READER_TOOLBAR_TOP` as a number: below `lg`, a citation lands under
 * where the toolbar rests once stuck, not where it happens to be (IR-354).
 */
export const READER_TOOLBAR_TOP_PX = 64;
