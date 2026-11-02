/**
 * A citation landing in the Review section (IR-412, IR-477; spec Appendix K, IR-354).
 *
 * The Review section reuses `PaperPdfReader`, so a citation lands
 * by the reader's own rule (`citationLandingDelta`). What the Review section
 * adds is what could cover the passage once it lands: at `lg` the review pane
 * beside the reader, and below `lg` the action bar stuck to the bottom of
 * the screen. These check, with IR-354's helper and the reader's own band
 * (`windowReadingBand`), that the landed passage clears the header and that
 * pane or bar alike.
 *
 * Below `lg` the author's Review tab gives the reader its bar's measured
 * height (`bottomInset`, IR-477; spec Appendix K, amended), so the reader's
 * band stops above the bar rather than at the bottom of the window. These
 * cases are arithmetic on the section's measured geometry, not a rendered
 * layout, which jsdom cannot measure (spec §5). The browser check at
 * 360×740 with a passage taller than 350px is IR-477's own acceptance
 * criterion, recorded on its PR.
 *
 * The bar's height is measured in a browser (IR-412's PR): one row of 44px
 * controls is 60px tall at 768px wide; at 360px the controls wrap to two
 * rows, 112px (headless Chrome, 2026-10-07).
 */
import { describe, expect, it } from "vitest";

import { PANE_TOP_PX } from "./paneLayout";
import { CITATION_CONTEXT, citationLandingDelta, windowReadingBand } from "./readerGeometry";

/** The action bar below `lg` at its tallest: two rows at 360px. */
const ACTION_BAR_TWO_ROWS_PX = 112;

describe("a citation landing in the Review section", () => {
  // A 360×740 phone. The reader's toolbar sticks under the header and wraps
  // to two rows of 44px controls at this width.
  const TOOLBAR_TWO_ROWS_PX = 2 * 44 + 4 + 2 * 6;
  const view = windowReadingBand(TOOLBAR_TWO_ROWS_PX, 740, ACTION_BAR_TWO_ROWS_PX);
  const barTop = 740 - ACTION_BAR_TWO_ROWS_PX;

  /** Where a passage `height` px tall, a tenth of the way down a page, comes to rest. */
  function landed(height: number) {
    const page = { top: 1800, height: 1000 };
    const region = { top: 0.1, bottom: 0.1 + height / 1000 };
    const delta = citationLandingDelta(page, region, view);
    return { top: page.top + region.top * page.height - delta, bottom: page.top + region.bottom * page.height - delta };
  }

  it("clears the header and the sticky action bar below lg", () => {
    const passage = landed(24);
    expect(passage.top).toBe(view.top + CITATION_CONTEXT);
    expect(passage.bottom).toBeLessThanOrEqual(barTop);
  });

  it("lands a passage taller than 350px, a long table, 48px under the toolbar and clear of the bar", () => {
    const passage = landed(400);
    expect(passage.top).toBe(view.top + CITATION_CONTEXT);
    expect(passage.bottom).toBeLessThanOrEqual(barTop);
  });

  it("gives up context rather than end a passage under the bar, while the passage still fits above it", () => {
    // 450px: with the band running to the window's bottom it landed 48px
    // under the toolbar and its last 38px ended under the bar.
    const passage = landed(450);
    expect(passage.top).toBeGreaterThanOrEqual(view.top);
    expect(passage.bottom).toBe(barTop);
  });

  it("keeps a passage taller than the room above the bar at the toolbar, its end running on past", () => {
    const passage = landed(600);
    expect(passage.top).toBe(view.top);
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
