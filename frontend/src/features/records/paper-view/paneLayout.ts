/**
 * The Paper View's sticky and pane geometry (IR-351, IR-352, IR-356).
 *
 * Top to bottom: the fixed 58px `Header`; 8px below it the floating
 * Abstract / Paper switch, 48px tall; 12px below that the panes -- the
 * reader, the docked Paper Chat and the rail -- which share one height so
 * their tops and bottoms line up, ending at the page's 28px bottom padding.
 *
 * Whole class strings, because Tailwind only generates classes it finds
 * written out in source. There are no spacing tokens for these offsets; they
 * are derived from the header's own `h-[58px]` and live here once. Change the
 * header, the switch or the `icon` Button's 44px, and these change with it.
 */

/** Where the reader becomes a contained pane: Tailwind's `lg`, 1024px. */
export const CONTAINED_LAYOUT_QUERY = "(min-width: 1024px)";

/** The floating view switch: 8px below the 58px header. */
export const VIEW_SWITCH_TOP = "top-[66px]";

/** Panes: 12px below the switch (66 + 48 + 12). */
export const PANE_TOP = "lg:top-[126px]";

/** The viewport less everything above a pane and the 28px bottom padding. */
export const PANE_HEIGHT = "lg:h-[calc(100vh-154px)]";
export const PANE_MAX_HEIGHT = "lg:max-h-[calc(100vh-154px)]";

/** Below `lg` the reader's toolbar sticks 8px under the switch instead. */
export const READER_TOOLBAR_TOP = "top-[122px]";

/**
 * Where a page scrolled to comes to rest: below `lg`, clear of the header,
 * the switch and the sticky toolbar (whose 44px controls end it ~180px
 * down); inside the pane, just below the pane's own toolbar.
 */
export const PAGE_SCROLL_MARGIN = "scroll-mt-[188px] lg:scroll-mt-4";
