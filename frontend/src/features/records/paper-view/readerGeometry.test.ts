/**
 * The arithmetic behind the contained reader (IR-352): what zoom fits a page
 * to its pane, and where the reader is, so a zoom change can put them back.
 *
 * Pure functions, so they are tested here without a DOM; jsdom has no layout,
 * and the component tests can only check that the reader uses them.
 */
import { describe, expect, it } from "vitest";

import {
  CITATION_CONTEXT,
  MAX_SCALE,
  MIN_SCALE,
  PAGE_LANDING_GAP,
  anchorDelta,
  citationLandingDelta,
  firstRegionOn,
  fitScale,
  readingAnchor,
  regionInView,
} from "./readerGeometry";

describe("fitScale", () => {
  it("fits a page's width to the pane, less the page's 1px border each side", () => {
    // A US Letter page is 612pt wide at scale 1.
    expect(fitScale(612, 808)).toBe(1.31);
  });

  it("rounds down, so the page never ends up a fraction wider than the pane", () => {
    const scale = fitScale(612, 776) ?? Infinity;
    expect(612 * scale + 2).toBeLessThanOrEqual(776);
  });

  it("stays within the zoom range the controls allow", () => {
    expect(fitScale(612, 100)).toBe(MIN_SCALE);
    expect(fitScale(612, 4000)).toBe(MAX_SCALE);
  });

  it("has nothing to fit to until the pane has been measured", () => {
    expect(fitScale(612, 0)).toBeNull();
    expect(fitScale(0, 800)).toBeNull();
  });
});

describe("readingAnchor", () => {
  // Three 1000px pages with a 16px gap, the view's top edge at y = 100.
  const pages = [
    { top: -1500, height: 1000 },
    { top: -484, height: 1000 },
    { top: 532, height: 1000 },
  ];

  it("names the page under the top of the view, and how far into it", () => {
    expect(readingAnchor(pages, 100)).toEqual({ page: 2, fraction: 0.584 });
  });

  it("is the first page, from its top, before anything has scrolled", () => {
    const unscrolled = [
      { top: 150, height: 1000 },
      { top: 1166, height: 1000 },
    ];
    expect(readingAnchor(unscrolled, 100)).toEqual({ page: 1, fraction: 0 });
  });

  it("moves on to the next page when the previous one ends a sub-pixel past the view's top", () => {
    // A page scrolled to rests with the page above it ending exactly at the
    // view's top edge; rounding can leave that edge a fraction past it.
    const landed = [
      { top: -899.8, height: 1000 },
      { top: 116, height: 1000 },
    ];
    expect(readingAnchor(landed, 99.8)).toEqual({ page: 2, fraction: 0 });
  });

  it("is the last page once the view is past every page", () => {
    expect(readingAnchor([{ top: -3000, height: 1000 }], 100)).toEqual({ page: 1, fraction: 1 });
  });

  it("is nothing when there are no pages", () => {
    expect(readingAnchor([], 100)).toBeNull();
  });
});

describe("anchorDelta", () => {
  it("is how far to scroll so the same point of the page is back at the top of the view", () => {
    // After a zoom the page is 1300px tall and its top moved to y = -200.
    // 58.4% down it is at -200 + 759.2 = 559.2; the view's top is at 100.
    expect(anchorDelta({ top: -200, height: 1300 }, 0.584, 100)).toBeCloseTo(459.2);
  });

  it("is zero when the point is already at the top of the view", () => {
    expect(anchorDelta({ top: 100, height: 1000 }, 0, 100)).toBe(0);
  });
});

describe("citationLandingDelta (IR-354)", () => {
  // A 1000px page whose top is 2000px down; readable from y = 180 (below the
  // header and the reader's toolbar) to the bottom of a 780px window.
  const page = { top: 2000, height: 1000 };
  const view = { top: 180, bottom: 780 };

  it("lands the region's top, not the page's, just below the view's top with some context above it", () => {
    const delta = citationLandingDelta(page, { top: 0.85, bottom: 0.9 }, view);

    // The region starts at 2000 + 850 = 2850.
    expect(delta).toBe(2850 - 180 - CITATION_CONTEXT);
    // After scrolling, the whole region is inside the view.
    const regionTop = 2850 - delta;
    const regionBottom = 2900 - delta;
    expect(regionTop).toBeGreaterThanOrEqual(view.top);
    expect(regionBottom).toBeLessThanOrEqual(view.bottom);
  });

  it("keeps a region at the very top of a page below the view's top too", () => {
    const delta = citationLandingDelta(page, { top: 0.02, bottom: 0.05 }, view);

    expect(2020 - delta).toBe(view.top + CITATION_CONTEXT);
  });

  it("gives up context rather than push a tall region's end out of the view", () => {
    // 580px of region in a 600px view leaves room for 20px of context only.
    const tall = citationLandingDelta(page, { top: 0.1, bottom: 0.68 }, view);
    expect(2100 - tall).toBeCloseTo(view.top + 20);

    // Taller than the view: its top lands at the view's top, and no higher.
    const taller = citationLandingDelta(page, { top: 0.1, bottom: 0.9 }, view);
    expect(2100 - taller).toBe(view.top);
  });

  it("lands on the page's top edge, clear of the view's top, when there is no region", () => {
    const delta = citationLandingDelta(page, null, view);

    expect(2000 - delta).toBe(view.top + PAGE_LANDING_GAP);
  });
});

describe("firstRegionOn (IR-354)", () => {
  it("is the page's first region in reading order, ignoring the other pages", () => {
    // A two-column page: the passage starts low in the left column and
    // carries on at the top of the right one. It lands on its start.
    const regions = [
      { page: 4, left: 0.1, top: 0.1, right: 0.9, bottom: 0.2 },
      { page: 5, left: 0.05, top: 0.8, right: 0.48, bottom: 0.9 },
      { page: 5, left: 0.52, top: 0.1, right: 0.95, bottom: 0.2 },
    ];

    expect(firstRegionOn(regions, 5)).toEqual(regions[1]);
  });

  it("is nothing when the page has no region", () => {
    expect(firstRegionOn([{ page: 4, left: 0, top: 0, right: 1, bottom: 1 }], 5)).toBeNull();
  });
});

describe("regionInView (IR-353)", () => {
  // A 1000px page 100px down a view from 200px to 800px.
  const page = { top: 100, height: 1000 };
  const view = { top: 200, bottom: 800 };

  it("is true for a band wholly inside the view", () => {
    expect(regionInView(page, { top: 0.2, bottom: 0.25 }, view)).toBe(true);
  });

  it("is false for a band under the toolbar, or below the view", () => {
    expect(regionInView(page, { top: 0.05, bottom: 0.12 }, view)).toBe(false);
    expect(regionInView(page, { top: 0.68, bottom: 0.72 }, view)).toBe(false);
  });
});
