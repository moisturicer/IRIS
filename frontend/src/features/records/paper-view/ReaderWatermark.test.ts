import { describe, expect, it } from "vitest";

import { MARK_LINES, markLineWidth } from "./ReaderWatermark";

describe("the reader's mark (IR-1198)", () => {
  it("reads PROPERTY OF / CIT-U / DO NOT DISTRIBUTE", () => {
    expect(MARK_LINES).toEqual(["PROPERTY OF", "CIT-U", "DO NOT DISTRIBUTE"]);
  });

  it("has the download copy's line widths, so the two marks are one shape", () => {
    // test_download_watermark.MarkWordingTests pins the same numbers.
    expect(MARK_LINES.map((line) => Math.round(markLineWidth(line) * 1e6) / 1e6)).toEqual([11.6, 4.5, 16.6]);
  });
});
