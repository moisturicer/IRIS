/**
 * The pane offsets exist twice: as whole Tailwind classes, which Tailwind
 * only generates when it finds them written out, and as numbers, which the
 * reader scrolls by (IR-354). This keeps the two from drifting apart.
 */
import { describe, expect, it } from "vitest";

import { PANE_TOP, PANE_TOP_PX, READER_TOOLBAR_TOP, READER_TOOLBAR_TOP_PX } from "./paneLayout";

describe("pane offsets", () => {
  it("scrolls the pane to where it is drawn", () => {
    expect(PANE_TOP).toBe(`lg:top-[${PANE_TOP_PX}px]`);
  });

  it("lands a citation under where the reader's toolbar is drawn", () => {
    expect(READER_TOOLBAR_TOP).toBe(`top-[${READER_TOOLBAR_TOP_PX}px]`);
  });
});
