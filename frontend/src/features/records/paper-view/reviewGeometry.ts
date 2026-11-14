/**
 * The Review workspace's geometry (IR-1094; spec §4.8). The workspace lays
 * itself out by its own width, not the window's: paper and pane side by side,
 * then a drawer; one tab may open on the right where there is room.
 *
 * CSS and React must agree on the drawer's breakpoint, so both read it here:
 * `reviewWorkspace.css` states it as a container query and a test keeps them equal.
 */

/** Narrower than this the pane is a drawer over the paper, with *Back to paper*. */
export const DRAWER_BELOW_PX = 900;

/** From this workspace width a tab may open on the right and the paper keeps its room. */
export const SIDE_TAB_MIN_PX = 1180;

/** The paper never gets less than this, so the pane and a right column share the rest. */
export const PAPER_MIN_PX = 480;

/** The pane's width when nobody has chosen one, as far as half the workspace allows. */
export const PANE_DEFAULT_PX = 520;
export const PANE_MIN_PX = 320;
export const SIDE_DEFAULT_PX = 320;
export const SIDE_MIN_PX = 220;
export const SIDE_MAX_PX = 420;

/** Before the container is measured, and in jsdom, the layout assumes a wide workspace. */
export const UNMEASURED_PX = 1600;

export type Widths = { mid: number | null; side: number | null };

/**
 * One geometry for pointer, keyboard, restored widths and container changes.
 * Two columns by default, the pane getting 520px; a right column shares what
 * the paper's minimum leaves. `side` is kept even while no tab is open there,
 * so the width comes back with it.
 */
export function fitWidths(width: number, wanted: Widths, sideOpen: boolean) {
  const w = width || UNMEASURED_PX;
  const room = w - PAPER_MIN_PX;
  const side = Math.max(SIDE_MIN_PX, Math.min(wanted.side ?? SIDE_DEFAULT_PX, SIDE_MAX_PX, room - PANE_MIN_PX));
  const mid = Math.max(PANE_MIN_PX, Math.min(wanted.mid ?? Math.min(PANE_DEFAULT_PX, w / 2), w / 2, room - (sideOpen ? side : 0)));
  return { mid: Math.floor(mid), side: Math.floor(side) };
}

/** The least a column may be: the separator's `aria-valuemin`. */
export const minWidth = (key: keyof Widths) => (key === "mid" ? PANE_MIN_PX : SIDE_MIN_PX);

/** What the arrow keys and a drag may reach: the separator's `aria-valuemax`. */
export function maxWidth(key: keyof Widths, width: number, sizes: { mid: number; side: number }, sideOpen: boolean) {
  const w = width || UNMEASURED_PX;
  return key === "mid"
    ? Math.max(PANE_MIN_PX, Math.min(w / 2, w - PAPER_MIN_PX - (sideOpen ? sizes.side : 0)))
    : Math.max(SIDE_MIN_PX, Math.min(SIDE_MAX_PX, w - PAPER_MIN_PX - sizes.mid));
}
