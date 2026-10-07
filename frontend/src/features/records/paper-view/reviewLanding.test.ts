/**
 * A citation landing in the Review section (IR-412; spec Appendix K, IR-354).
 *
 * The Review section reuses `PaperPdfReader` unchanged, so a citation lands
 * by the reader's own rule (`citationLandingDelta`). What the Review section
 * adds is what could cover the passage once it lands: at `lg` the review pane
 * beside the reader, and below `lg` the action bar stuck to the bottom of
 * the screen. These check, with IR-354's helper rather than a new one, that
 * the landed passage clears the header and that pane or bar alike.
 *
 * **What this does not prove.** The reader is unchanged (Appendix K), so it is
 * told nothing about the bar: its view runs to the bottom of the window. A
 * passage lands 48px under the reader's toolbar, so it clears the bar only
 * while it is shorter than the room left above the bar -- about 350px at
 * 360×740. A taller one ends under the bar. These cases pin that room; they
 * are arithmetic on the section's measured geometry, not a rendered layout,
 * which jsdom cannot measure (spec §5). The layout itself was checked in a
 * browser at the four viewports.
 *
 * The bar's height is measured in a browser (IR-412's PR): one row of 44px
 * controls is 60px tall at 768px wide; at 360px the controls wrap to two
 * rows, 112px (headless Chrome, 2026-10-07).
 */
import { describe, expect, it } from "vitest";

import { PANE_TOP_PX, READER_TOOLBAR_TOP_PX } from "./paneLayout";
import { CITATION_CONTEXT, citationLandingDelta } from "./readerGeometry";

/** The action bar below `lg` at its tallest: two rows at 360px. */
const ACTION_BAR_TWO_ROWS_PX = 112;

describe("a citation landing in the Review section", () => {
  it("clears the header and the sticky action bar below lg", () => {
    // A 360×740 phone. The reader's toolbar sticks under the header and the
    // section switch, and wraps to two rows of 44px controls at this width.
    const viewport = { height: 740 };
    const toolbarHeight = 2 * 44 + 4 + 2 * 6;
    const view = { top: READER_TOOLBAR_TOP_PX + toolbarHeight, bottom: viewport.height };

    // A passage a third of the way down page 3, two lines tall at this width.
    const page = { top: 1800, height: 470 };
    const region = { top: 0.35, bottom: 0.4 };
    const delta = citationLandingDelta(page, region, view);

    const regionTop = page.top + region.top * page.height - delta;
    const regionBottom = page.top + region.bottom * page.height - delta;
    expect(regionTop).toBe(view.top + CITATION_CONTEXT);
    expect(regionBottom).toBeLessThanOrEqual(viewport.height - ACTION_BAR_TWO_ROWS_PX);
  });

  it("clears the bar for a passage nearly half the phone's screen tall", () => {
    const view = { top: READER_TOOLBAR_TOP_PX + 104, bottom: 740 };
    const page = { top: 1800, height: 470 };
    // 340px of passage: most of a page at 360px wide. It lands 48px under
    // the toolbar (274px) and ends at 614px, above the bar at 628px.
    const region = { top: 0.1, bottom: 0.1 + 340 / 470 };
    const delta = citationLandingDelta(page, region, view);

    const regionBottom = page.top + region.bottom * page.height - delta;
    expect(regionBottom).toBeLessThanOrEqual(740 - ACTION_BAR_TWO_ROWS_PX);
  });

  it("lands under the reader's own toolbar at lg, which the review pane sits beside, not over", () => {
    // At `lg` the reader is a contained pane resting at `PANE_TOP_PX`; its
    // pages scroll under its toolbar, and the review pane is a column beside
    // it at the same top, so nothing of the section covers the scroll area.
    const toolbarBottom = PANE_TOP_PX + 45;
    const view = { top: toolbarBottom, bottom: 800 - 28 };
    const page = { top: 2400, height: 1035 };
    const region = { top: 0.6, bottom: 0.66 };
    const delta = citationLandingDelta(page, region, view);

    const regionTop = page.top + region.top * page.height - delta;
    const regionBottom = page.top + region.bottom * page.height - delta;
    expect(regionTop).toBeGreaterThanOrEqual(toolbarBottom);
    expect(regionBottom).toBeLessThanOrEqual(view.bottom);
  });
});
