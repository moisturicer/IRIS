/**
 * The pane offsets exist twice: as whole Tailwind classes, which Tailwind
 * only generates when it finds them written out, and as numbers, which the
 * reader scrolls by (IR-354). This keeps the two from drifting apart.
 */
import { describe, expect, it } from "vitest";

import {
  PANE_HEIGHT,
  PANE_TOP,
  PANE_TOP_PX,
  READER_TOOLBAR_TOP,
  READER_TOOLBAR_TOP_PX,
  VIEW_SWITCH_TOP,
} from "./paneLayout";

describe("pane offsets", () => {
  it("measures from the top of the window, now that no app header sits above (IR-519)", () => {
    // The switch rests 8px down; it is 48px tall; panes sit 12px under it and
    // the reader's toolbar 8px under it. The 28px is the page's bottom padding.
    expect(VIEW_SWITCH_TOP).toBe("top-[8px]");
    expect(PANE_TOP_PX).toBe(8 + 48 + 12);
    expect(READER_TOOLBAR_TOP_PX).toBe(8 + 48 + 8);
    expect(PANE_HEIGHT).toBe(`lg:h-[calc(100vh-${PANE_TOP_PX + 28}px)]`);
  });

  it("scrolls the pane to where it is drawn", () => {
    expect(PANE_TOP).toBe(`lg:top-[${PANE_TOP_PX}px]`);
  });

  it("lands a citation under where the reader's toolbar is drawn", () => {
    expect(READER_TOOLBAR_TOP).toBe(`top-[${READER_TOOLBAR_TOP_PX}px]`);
  });
});
