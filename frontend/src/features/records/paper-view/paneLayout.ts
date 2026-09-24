/**
 * The Paper View's panes at `lg` and up (IR-351, IR-352): the reader, the
 * docked Paper Chat and the rail all sit below the fixed 58px `Header` and
 * share one height, so their tops and bottoms line up.
 *
 * Whole class strings, because Tailwind only generates classes it finds
 * written out in source. There is no spacing token for these offsets; they
 * are derived from the header's own `h-[58px]`, and live here once.
 */

/** Where the reader becomes a contained pane: Tailwind's `lg`, 1024px. */
export const CONTAINED_LAYOUT_QUERY = "(min-width: 1024px)";

/** 24px below the 58px header. */
export const PANE_TOP = "lg:top-[82px]";

/**
 * The viewport less the header, the 24px gap above a pane and the page's
 * 28px bottom padding, so a pane ends exactly where the page does.
 */
export const PANE_HEIGHT = "lg:h-[calc(100vh-110px)]";
export const PANE_MAX_HEIGHT = "lg:max-h-[calc(100vh-110px)]";

/** Below `lg` the reader's toolbar sticks 8px under the header instead. */
export const READER_TOOLBAR_TOP = "top-[66px]";

/**
 * Where a page scrolled to comes to rest: below `lg`, clear of the header
 * and the sticky toolbar, whose 44px touch targets end it ~124px down;
 * inside the pane, just below the pane's own toolbar.
 */
export const PAGE_SCROLL_MARGIN = "scroll-mt-[132px] lg:scroll-mt-4";
