/**
 * Find in this paper's matching (IR-353), apart from any rendering: which
 * runs of which page a query matches, and where on the page each match is.
 */
import { describe, expect, it } from "vitest";

import type { TextRun } from "@/lib/pdf";

import { findMatches, firstMatchFrom, hitsOnPage, isSearchable } from "./findInPaper";

/** A run on its own line band, `top`..`top + 0.02` down the page. */
function run(str: string, top = 0.1, eol = false): TextRun {
  return { str, eol, top, bottom: top + 0.02 };
}

describe("findMatches", () => {
  it("finds nothing for an empty or blank query", () => {
    const pages = [[run("robots")]];

    expect(findMatches(pages, "")).toEqual([]);
    expect(findMatches(pages, "   ")).toEqual([]);
  });

  it("is case-insensitive, and counts every match on every page", () => {
    const pages = [
      [run("Robot policies for robots.")],
      [run("No match here.")],
      [run("A ROBOT arm.")],
    ];

    const matches = findMatches(pages, "robot");

    expect(matches.map((m) => m.page)).toEqual([1, 1, 3]);
    expect(matches[0].pieces).toEqual([{ run: 0, start: 0, end: 5 }]);
    expect(matches[1].pieces).toEqual([{ run: 0, start: 19, end: 24 }]);
  });

  it("does not count overlapping matches twice", () => {
    expect(findMatches([[run("aaaa")]], "aa")).toHaveLength(2);
  });

  it("matches across runs, and reads a line's end as a space", () => {
    const pages = [[run("vision ", 0.1), run("language", 0.1, true), run("action", 0.13)]];

    // The space inside the first run is part of the match; the one a line's
    // end stands for is not drawn, so it is not highlighted.
    const [joined] = findMatches(pages, "vision language");
    expect(joined.pieces).toEqual([
      { run: 0, start: 0, end: 7 },
      { run: 1, start: 0, end: 8 },
    ]);

    const [acrossLine] = findMatches(pages, "language action");
    expect(acrossLine.pieces).toEqual([
      { run: 1, start: 0, end: 8 },
      { run: 2, start: 0, end: 6 },
    ]);
  });

  it("treats any run of whitespace, in the paper or the query, as one space", () => {
    const pages = [[run("large   language\tmodel")]];

    expect(findMatches(pages, "  large language   model ")).toHaveLength(1);
  });

  it("gives each match the band of the page its runs occupy", () => {
    const pages = [[run("end of a ", 0.5, true), run("line", 0.53)]];

    const [match] = findMatches(pages, "a line");

    expect(match.region.top).toBeCloseTo(0.5);
    expect(match.region.bottom).toBeCloseTo(0.55);
  });

  it("skips pages whose text is not extracted yet, and numbers the rest correctly", () => {
    const pages = [undefined, [run("robot")]];

    expect(findMatches(pages, "robot").map((m) => m.page)).toEqual([2]);
  });
});

describe("firstMatchFrom", () => {
  const pages = [[run("robot")], [run("nothing")], [run("robot robot")]];
  const matches = findMatches(pages, "robot");

  it("is the first match on or after the page being read", () => {
    expect(firstMatchFrom(matches, 2)).toBe(1);
    expect(firstMatchFrom(matches, 3)).toBe(1);
  });

  it("wraps to the first match when none follows the page being read", () => {
    expect(firstMatchFrom(matches, 4)).toBe(0);
  });
});

describe("hitsOnPage", () => {
  it("lists the page's matches, and marks the current one", () => {
    const pages = [[run("robot")], [run("robot, robot")]];
    const matches = findMatches(pages, "robot");

    expect(hitsOnPage(matches, 2, 2)).toEqual([
      { pieces: [{ run: 0, start: 0, end: 5 }], current: false },
      { pieces: [{ run: 0, start: 7, end: 12 }], current: true },
    ]);
    expect(hitsOnPage(matches, 1, 2)).toEqual([
      { pieces: [{ run: 0, start: 0, end: 5 }], current: false },
    ]);
  });
});

describe("isSearchable", () => {
  it("is false for a paper whose pages carry no text, as a scan's do", () => {
    expect(isSearchable([[], [run("  ")]])).toBe(false);
  });

  it("is true once any page carries text", () => {
    expect(isSearchable([[], [run("robot")]])).toBe(true);
  });
});
