/**
 * The record page's sticky and pane geometry (IR-351, IR-352, IR-569).
 * The `reading` container's width picks the layout; CSS reads it through the
 * `reading-*` variants, React through `readingTier` (kept equal by the test).
 */

/** Ask IRIS beside the paper from here, leaving the paper at least 640px. */
export const READING_WIDE_PX = 1000;

/** Ask IRIS over the paper from here; one view at a time below it. */
export const READING_SPLIT_PX = 640;

export type ReadingTier = "wide" | "overlay" | "single";

/** The tier for a measured width, or null before there is one (and in jsdom). */
export function readingTier(width: number): ReadingTier | null {
  if (width <= 0) return null;
  if (width >= READING_WIDE_PX) return "wide";
  if (width >= READING_SPLIT_PX) return "overlay";
  return "single";
}

/** The sticky part of the reading header: all of it, or its tab row. */
export const READING_HEADER_PX = 56;

/** Panes: 12px below the header. */
export const PANE_TOP_PX = READING_HEADER_PX + 12;

/** Overview's rail and docked chat, which still follow the window (`lg`). */
export const PANE_TOP = "lg:top-[68px]";
export const PANE_HEIGHT = "lg:h-[calc(100vh-96px)]";
export const PANE_MAX_HEIGHT = "lg:max-h-[calc(100vh-96px)]";

/** The reader and the Review pane, which follow the workspace. */
export const READING_PANE_TOP = "reading-wide:top-[68px]";
export const READING_PANE_HEIGHT = "reading-wide:h-[calc(100vh-96px)]";

/** Below `reading-wide` the reader's toolbar sticks 8px under the header. */
export const READER_TOOLBAR_TOP = "top-[64px]";

/** Where the toolbar rests once stuck: a citation lands under that (IR-354). */
export const READER_TOOLBAR_TOP_PX = READING_HEADER_PX + 8;
