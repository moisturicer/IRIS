/**
 * The arithmetic behind the contained reader (IR-352), kept apart from the
 * component so it can be tested without layout, which jsdom does not have.
 */
import type { Region } from "@/types/ai";

import { READER_TOOLBAR_TOP_PX } from "./paneLayout";

/** The zoom range the reader's controls allow. The floor is low enough that
 *  fit-to-width still fits a US Letter page on a 360px phone (NFR-U3). */
export const MIN_SCALE = 0.4;
export const MAX_SCALE = 2.4;

/** A page's 1px border, each side, which is drawn outside its canvas. */
const PAGE_BORDER = 2;

/** How far past the view's top a page must reach to count as in view. */
const EDGE_TOLERANCE = 1;

/**
 * The zoom at which a page `baseWidth` wide at scale 1 fills `available`
 * pixels, or `null` when either is not known yet.
 *
 * Rounded *down* to a hundredth: rounding to nearest could leave the page a
 * pixel wider than its pane, and a horizontal scrollbar for one pixel.
 */
export function fitScale(baseWidth: number, available: number): number | null {
  if (baseWidth <= 0 || available <= 0) return null;
  const exact = (available - PAGE_BORDER) / baseWidth;
  const rounded = Math.floor(exact * 100) / 100;
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, rounded));
}

export interface PageBox {
  top: number;
  height: number;
}

/** Where the reader is: a page (1-based), and how far down it (0..1). */
export interface ReadingAnchor {
  page: number;
  fraction: number;
}

/**
 * The page under the top edge of the view (`viewTop`, in the same
 * coordinates as the boxes), and how far into it that edge falls.
 *
 * It is what "Page n / N" shows, and what a zoom change restores: a
 * fraction of a page survives a change of scale, a pixel offset does not.
 */
export function readingAnchor(pages: PageBox[], viewTop: number): ReadingAnchor | null {
  if (pages.length === 0) return null;
  for (let i = 0; i < pages.length; i += 1) {
    const { top, height } = pages[i];
    // A page that ends less than a pixel into the view is behind the reader:
    // a page scrolled to rests with the one above ending at the view's top,
    // and sub-pixel rounding must not name the page above instead.
    if (top + height > viewTop + EDGE_TOLERANCE) {
      const fraction = height > 0 ? (viewTop - top) / height : 0;
      return { page: i + 1, fraction: Math.min(1, Math.max(0, fraction)) };
    }
  }
  return { page: pages.length, fraction: 1 };
}

/**
 * How far to scroll so the point `fraction` of the way down `page` is back
 * at `viewTop`. Positive scrolls down.
 */
export function anchorDelta(page: PageBox, fraction: number, viewTop: number): number {
  return page.top + fraction * page.height - viewTop;
}

/** Room left above a cited passage when it lands: a line or two of what leads into it. */
export const CITATION_CONTEXT = 48;

/** Room left above a page when a citation lands on the page alone. */
export const PAGE_LANDING_GAP = 16;

/**
 * The band of the screen a passage can be read in: from under the header
 * and the reader's toolbar down to the bottom of what is visible. In the
 * same coordinates as the page's box -- the viewport's, as measured.
 */
export interface ReadingBand {
  top: number;
  bottom: number;
}

/**
 * The reading band when the window scrolls, below `reading-wide`: from under
 * the reader's toolbar, where it rests once stuck, down to the bottom of the
 * window less `bottomInset` -- whatever the caller keeps stuck over the
 * bottom of the screen, as the Review tab does its action bar (IR-477).
 */
export function windowReadingBand(toolbarHeight: number, windowHeight: number, bottomInset = 0): ReadingBand {
  return { top: READER_TOOLBAR_TOP_PX + toolbarHeight, bottom: windowHeight - bottomInset };
}

/**
 * How far to scroll so a citation lands where it can be read (IR-354).
 * Positive scrolls down.
 *
 * With a region -- a fraction of the page's height, as a citation carries
 * it -- the region's top comes to rest `CITATION_CONTEXT` below the view's
 * top, or less where a tall region would otherwise run out of the view;
 * never above the view's top. Without one, the page's top edge rests just
 * below the view's top, as a page scrolled to would.
 */
export function citationLandingDelta(
  page: PageBox,
  region: RegionBand | null,
  view: ReadingBand,
): number {
  if (!region) return page.top - view.top - PAGE_LANDING_GAP;
  const regionTop = page.top + region.top * page.height;
  const regionHeight = (region.bottom - region.top) * page.height;
  const spare = view.bottom - view.top - regionHeight;
  const context = Math.min(CITATION_CONTEXT, Math.max(0, spare));
  return regionTop - view.top - context;
}

/**
 * The region a citation should land on: its first on `page`. Regions arrive
 * in reading order (`apps/ai/regions.py`), so in a two-column paper a
 * passage starting low in the left column lands on its start, not on its
 * continuation at the top of the right one.
 */
export function firstRegionOn(regions: Region[], page: number): Region | null {
  return regions.find((region) => region.page === page) ?? null;
}

/** A band of a page, as fractions of its height: a region or a find match. */
export type RegionBand = Pick<Region, "top" | "bottom">;

/**
 * Whether `region` of `page` lies wholly inside `view` (IR-353). Find
 * leaves a match the reader can already see where it is, as a browser's
 * find does, rather than jumping the paper on every "next".
 */
export function regionInView(page: PageBox, region: RegionBand, view: ReadingBand): boolean {
  const top = page.top + region.top * page.height;
  const bottom = page.top + region.bottom * page.height;
  return top >= view.top && bottom <= view.bottom;
}

/** Pages kept live either side of the ones in view, so a short scroll finds them painted. */
export const LIVE_BUFFER = 2;

/**
 * The most pages that carry a canvas and a text layer at once (IR-565). At
 * the lowest zoom a tall screen shows a few pages; this leaves room for those,
 * the buffer either side, and a page a citation or a find is landing on.
 */
export const MAX_LIVE_PAGES = 10;

/**
 * The pages to paint (IR-565): those from `first` to `last` in view, `LIVE_BUFFER`
 * either side, and each `pinned` page -- one a citation or a find is about to
 * land on, which is painted before the reader is moved there. Ascending, and
 * never more than `MAX_LIVE_PAGES`: the buffer gives way first, then the end
 * of a view showing more pages than that.
 *
 * Every other page stays an empty box of its own measured size, so the
 * scroll geometry is the same whichever pages are live.
 */
export function liveWindow(
  first: number,
  last: number,
  pageCount: number,
  pinned: (number | null)[],
): number[] {
  if (pageCount < 1) return [];
  const clamp = (n: number) => Math.min(pageCount, Math.max(1, n));
  const lo = clamp(first);
  const hi = clamp(Math.max(first, last));
  let start = clamp(lo - LIVE_BUFFER);
  let end = clamp(hi + LIVE_BUFFER);

  const pins = [...new Set(pinned)].filter((n): n is number => n !== null && n >= 1 && n <= pageCount);
  const outside = (n: number) => n < start || n > end;
  const room = () => MAX_LIVE_PAGES - pins.filter(outside).length;
  while (end - start + 1 > room() && end > hi) end -= 1;
  while (end - start + 1 > room() && start < lo) start += 1;
  while (end - start + 1 > room()) end -= 1;

  const live = new Set<number>(pins);
  for (let n = start; n <= end; n += 1) live.add(n);
  return [...live].sort((a, b) => a - b);
}
