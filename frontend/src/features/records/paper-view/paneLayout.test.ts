/**
 * The pane offsets exist twice: as whole Tailwind classes, which Tailwind
 * only generates when it finds them written out, and as numbers, which the
 * reader scrolls by (IR-354). The workspace thresholds exist twice too: as
 * the container variants CSS lays out by, and as numbers React decides focus
 * and panel state by (IR-569). This keeps each pair from drifting apart.
 */
import { describe, expect, it } from "vitest";

// @ts-expect-error -- the config is plain JS and ships no declaration file
import { readingVariants } from "../../../../tailwind.config.js";
import {
  OVERVIEW_ASIDE_MAX_HEIGHT,
  OVERVIEW_ASIDE_TOP,
  PANE_TOP_PX,
  READER_TOOLBAR_TOP,
  READER_TOOLBAR_TOP_PX,
  READING_HEADER_PX,
  READING_PANE_HEIGHT,
  READING_PANE_TOP,
  READING_SPLIT_PX,
  READING_WIDE_PX,
  readingTier,
} from "./paneLayout";

describe("pane offsets", () => {
  it("puts the panes 12px under the reading header", () => {
    expect(PANE_TOP_PX).toBe(READING_HEADER_PX + 12);
    expect(READING_PANE_TOP).toBe(`reading-wide:top-[${PANE_TOP_PX}px]`);
    expect(OVERVIEW_ASIDE_TOP).toBe(`overview-wide:top-[${PANE_TOP_PX}px]`);
  });

  it("ends the panes at the page's 28px bottom padding", () => {
    expect(READING_PANE_HEIGHT).toBe(`reading-wide:h-[calc(100vh-${PANE_TOP_PX + 28}px)]`);
    expect(OVERVIEW_ASIDE_MAX_HEIGHT).toBe(`overview-wide:max-h-[calc(100vh-${PANE_TOP_PX + 28}px)]`);
  });

  it("lands a citation under where the reader's toolbar sticks, 8px under the header", () => {
    expect(READER_TOOLBAR_TOP_PX).toBe(READING_HEADER_PX + 8);
    expect(READER_TOOLBAR_TOP).toBe(`top-[${READER_TOOLBAR_TOP_PX}px]`);
  });
});

describe("the workspace tiers (IR-569)", () => {
  it.each([
    [0, null],
    [360, "single"],
    [639, "single"],
    [640, "overlay"],
    [924, "overlay"],
    [999, "overlay"],
    [1000, "wide"],
    [1745, "wide"],
  ] as const)("reads %ipx as %s", (width, tier) => {
    expect(readingTier(width)).toBe(tier);
  });

  it("uses the same thresholds as the CSS container variants", () => {
    expect(readingVariants["reading-split"]).toBe(`@container reading (min-width: ${READING_SPLIT_PX}px)`);
    expect(readingVariants["reading-wide"]).toBe(`@container reading (min-width: ${READING_WIDE_PX}px)`);
  });

  it("leaves the reader at least 640px beside the widest panel", () => {
    // The panel is clamp(20rem, 100cqi - 656px, 22.5rem) with a 16px gap.
    const panel = (width: number) => Math.min(360, Math.max(320, width - 656));
    for (const width of [READING_WIDE_PX, 1016, 1280, 1745]) {
      expect(width - panel(width) - 16).toBeGreaterThanOrEqual(640);
    }
  });
});
