import { describe, expect, it } from "vitest";

import { contextAround, regionsFromRects } from "./passage";

const rect = (left: number, top: number, width: number, height: number) =>
  ({ left, top, right: left + width, bottom: top + height, width, height });

describe("regionsFromRects", () => {
  const pages = [
    { page: 3, box: rect(100, 0, 400, 800) },
    { page: 4, box: rect(100, 820, 400, 800) },
  ];

  it("measures each line as fractions of the page it is on", () => {
    expect(regionsFromRects([rect(140, 80, 200, 16)], pages)).toEqual([
      { page: 3, left: 0.1, top: 0.1, right: 0.6, bottom: 0.12 },
    ]);
  });

  it("splits a selection across two pages by page", () => {
    const regions = regionsFromRects([rect(140, 780, 100, 16), rect(140, 900, 100, 16)], pages);
    expect(regions.map((r) => r.page)).toEqual([3, 4]);
  });

  it("drops empty rects and clips to the page", () => {
    expect(regionsFromRects([rect(140, 80, 0, 16), rect(50, 790, 600, 40)], pages)).toEqual([
      { page: 3, left: 0, top: 0.9875, right: 1, bottom: 1 },
    ]);
  });
});

describe("contextAround", () => {
  it("keeps the text either side of the quote, whitespace collapsed", () => {
    const page = ["Methods.  The sensor reports", "an accuracy of 94% against   gauges in the field."].join("\n");
    expect(contextAround(page, "an accuracy  of 94%", 12)).toEqual({
      prefix: "sor reports ", suffix: " against gau",
    });
  });

  it("gives nothing when the quote isn't on the page", () => {
    expect(contextAround("Other text.", "missing", 12)).toEqual({ prefix: "", suffix: "" });
  });
});
