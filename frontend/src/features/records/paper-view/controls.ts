/**
 * The reading surfaces' controls, stated once (IR-569; 01-design-system §0).
 *
 * A control is 44px on a touch-sized workspace and 36px beside a pointer, with
 * a `rounded-lg` shape and 13px semibold text. Icon-only controls are the same
 * size square. A page action (View, Save, Cite, Share) is the other thing: a
 * 44px pill from `components/ui/pillStyles.ts`. `readingStandards.test.ts`
 * fails when a file in this folder goes back to its own heights and radii.
 *
 * The sizes read the `reading` container, not the window, so the sidebar
 * and Ask IRIS beside a paper change them too.
 */

/** 44px on touch, 36px beside a pointer. */
export const CONTROL_SIZE = "min-h-11 reading-split:min-h-9";

/** The same, for a control with no label. */
export const CONTROL_SQUARE = "w-11 h-11 reading-split:w-9 reading-split:h-9";

export const CONTROL_SHAPE = "rounded-lg";

export const CONTROL_TEXT = "text-small font-semibold";

/** Every control starts here; the rest are what it is doing. */
export const CONTROL_BASE = `inline-flex items-center gap-1.5 ${CONTROL_SIZE} ${CONTROL_SHAPE} ${CONTROL_TEXT} transition-colors duration-200`;

/** At rest: outlined, so the page has one filled thing at a time. */
export const CONTROL_OUTLINE = "border border-stone-300 text-stone-700 hover:border-brand/40 hover:text-brand";

/** Switched on: a quiet maroon tint. */
export const CONTROL_ON = "bg-brand-50 border border-brand-200 text-brand hover:border-brand/50";

/** The one filled control (Send). */
export const CONTROL_FILLED = "bg-brand border border-brand text-white hover:bg-brand-light disabled:opacity-30";
