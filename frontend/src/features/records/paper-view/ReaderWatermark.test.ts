import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MARK_LINES, ReaderWatermark, markLineWidth, markPath } from "./ReaderWatermark";

describe("the reader's mark (IR-1198)", () => {
  it("reads PROPERTY OF / CIT-U / DO NOT DISTRIBUTE", () => {
    expect(MARK_LINES).toEqual(["PROPERTY OF", "CIT-U", "DO NOT DISTRIBUTE"]);
  });

  it("has the download copy's line widths, so the two marks are one shape", () => {
    // test_download_watermark.MarkWordingTests pins the same numbers.
    expect(MARK_LINES.map((line) => Math.round(markLineWidth(line) * 1e6) / 1e6)).toEqual([11.6, 4.5, 16.6]);
  });

  it("cuts every line to one height, as the download copy does", () => {
    // test_download_watermark.MarkWordingTests pins the same bands: a letter and a stroke tall each.
    expect(markPath().bands.map(({ y, height }) => [y, height])).toEqual([
      [1.08, 1.24],
      [-0.62, 1.24],
      [-2.32, 1.24],
    ]);
  });

  it("draws the letters only inside those bands", () => {
    const html = renderToStaticMarkup(createElement(ReaderWatermark, { width: 612, height: 792, scale: 1 }));
    const id = /<clipPath id="([^"]+)">(?:<rect [^>]*><\/rect>){3}<\/clipPath>/.exec(html)?.[1];
    expect(id).toBeTruthy();
    expect(html).toContain(`clip-path="url(#${id})"`);
  });
});
