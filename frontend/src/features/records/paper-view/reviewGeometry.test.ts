/**
 * The Review workspace's geometry (IR-1094; spec §4.8).
 *
 * jsdom has no layout, so what "no blank band" and "no pane over the paper"
 * mean is pinned where they are decided: the numbers here, and the stylesheet
 * that must agree with them.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { DRAWER_BELOW_PX, fitWidths, maxWidth, PAPER_MIN_PX, SIDE_TAB_MIN_PX } from "./reviewGeometry";

const css = readFileSync(resolve(__dirname, "reviewWorkspace.css"), "utf8");
const none = { mid: null, side: null };

describe("the widths at 1440, 1024 and 768 (IR-1094)", () => {
  it.each([1440, 1024])("lays paper and pane side by side at %ipx, the pane 520px or half the workspace", (w) => {
    const { mid } = fitWidths(w, none, false);
    expect(mid).toBe(Math.min(520, w / 2));
    expect(w - mid).toBeGreaterThanOrEqual(PAPER_MIN_PX);
    expect(w).toBeGreaterThanOrEqual(DRAWER_BELOW_PX);
  });

  it("is a drawer at 768px, narrower than the breakpoint", () => {
    expect(768).toBeLessThan(DRAWER_BELOW_PX);
  });

  it("never gives the pane and a right column more than the paper's minimum leaves", () => {
    for (const w of [1180, 1200, 1440, 1920]) {
      const { mid, side } = fitWidths(w, { mid: 5000, side: 5000 }, true);
      expect(w - mid - side).toBeGreaterThanOrEqual(PAPER_MIN_PX);
      expect(maxWidth("mid", w, { mid, side }, true)).toBeGreaterThanOrEqual(mid);
    }
  });

  it("keeps the right column's width while it is closed, so it comes back as it was", () => {
    expect(fitWidths(1600, { mid: null, side: 360 }, false).side).toBe(360);
  });

  it("offers a right column from 1180px, where the paper keeps its room even with both", () => {
    const { mid, side } = fitWidths(SIDE_TAB_MIN_PX, none, true);
    expect(SIDE_TAB_MIN_PX - mid - side).toBeGreaterThanOrEqual(PAPER_MIN_PX);
  });
});

describe("the stylesheet agrees with the geometry (IR-1094)", () => {
  it("pins the workspace's one row, so a column scrolls inside itself and no band is left under it (LAY-07)", () => {
    expect(css).toMatch(/\.review-workspace \{[^}]*grid-template-rows: minmax\(0, 1fr\)/);
  });

  it("switches to the drawer at the same width React does", () => {
    expect(css).toContain(`@container review-workspace (max-width: ${DRAWER_BELOW_PX - 1}px)`);
  });

  it("has no breakpoint that folds the second column away between the drawer and wide (RES-06)", () => {
    const widths = [...css.matchAll(/@container review-workspace \(max-width: (\d+)px\)/g)].map((m) => Number(m[1]));
    expect(widths).toEqual([DRAWER_BELOW_PX - 1]);
  });

  it("has no People & details column", () => {
    expect(css).not.toContain(".review-details");
  });
});
