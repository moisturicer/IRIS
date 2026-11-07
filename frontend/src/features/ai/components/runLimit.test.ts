import { describe, expect, it } from "vitest";

import { BREAK, MAX_RUN_CHARS, breakLongRuns } from "./runLimit";

const longestRun = (text: string) => Math.max(0, ...(text.match(/\S+/g) ?? []).map((run) => run.length));

describe("breakLongRuns", () => {
  it("leaves ordinary text, links and formulas untouched", () => {
    const text = "See https://example.org/a?b=c+d, mail bob+x@example.com and $\\frac{a}{b}+c$.\n\n- item";
    expect(breakLongRuns(text)).toBe(text);
  });

  it("leaves a run of exactly the limit untouched", () => {
    const text = "x".repeat(MAX_RUN_CHARS);
    expect(breakLongRuns(text)).toBe(text);
  });

  it("leaves no stretch between breaks longer than the limit", () => {
    for (const unit of ["x+", "x-", "x.", "x_", "x", "a.b+"]) {
      const out = breakLongRuns(unit.repeat(40_000 / unit.length));
      // The break is not whitespace to the parser, but the email scan stops at
      // it, so the bound that matters is the distance between breaks.
      expect(longestRun(out.split(BREAK).join(" "))).toBeLessThanOrEqual(MAX_RUN_CHARS);
    }
  });

  it("is idempotent, and measures a run from a break that is already there", () => {
    const once = breakLongRuns("x+".repeat(5_000));
    expect(breakLongRuns(once)).toBe(once);
    const own = `${"y".repeat(MAX_RUN_CHARS)}${BREAK}${"y".repeat(MAX_RUN_CHARS)}`;
    expect(breakLongRuns(own)).toBe(own);
  });

  it("loses no characters: removing the breaks gives the input back", () => {
    const text = `before ${"x+".repeat(5_000)} after\n\n${"é".repeat(MAX_RUN_CHARS * 2 + 1)}`;
    expect(breakLongRuns(text).split(BREAK).join("")).toBe(text);
  });

  it("breaks each long run on its own and keeps the words between them", () => {
    const out = breakLongRuns(`a ${"y".repeat(MAX_RUN_CHARS + 1)} b ${"z".repeat(MAX_RUN_CHARS + 1)} c`);
    // Two runs of limit + 1, each cut once: two breaks, three pieces.
    expect(out.split(BREAK)).toHaveLength(3);
    expect(out).toContain(` b ${"z".repeat(MAX_RUN_CHARS)}${BREAK}z c`);
    expect(out.startsWith("a ")).toBe(true);
    expect(out.endsWith(" c")).toBe(true);
  });

  it("does not split a surrogate pair", () => {
    const out = breakLongRuns("😀".repeat(MAX_RUN_CHARS));
    for (const piece of out.split(BREAK)) {
      expect(piece).toBe(Array.from(piece).join(""));
      expect(/[\uD800-\uDBFF]$/.test(piece)).toBe(false);
      expect(/^[\uDC00-\uDFFF]/.test(piece)).toBe(false);
    }
  });
});
