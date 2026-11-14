/**
 * The highlight roles (IR-1097, D6): one look per kind of highlight, and no
 * look means two things. jsdom cannot measure colour, so the contrast of Ink
 * on the match yellow is computed here from the token values.
 */
import { describe, expect, it } from "vitest";
import resolveConfig from "tailwindcss/resolveConfig";

// @ts-expect-error -- the config is plain JS and ships no declaration file
import tailwindConfig from "../../../tailwind.config.js";

import { HERE, MATCH, REFERENCE, SELECTED, SELECTED_RING, SELECTED_SEGMENT } from "./highlightRoles";
import { PILL_SELECTED } from "./pillStyles";
import { TONES } from "./statusTones";

const colors = resolveConfig(tailwindConfig).theme.colors as Record<string, unknown>;

/** WCAG 2.x relative luminance of a `#rrggbb` colour. */
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const INK = (colors.stone as Record<string, string>)[900];
const hl = colors.hl as Record<string, string>;
const pen = colors.pen as Record<string, string>;

describe("the match highlighter", () => {
  it("keeps Ink at least 4.5:1 on the match and on the current match", () => {
    expect(contrast(INK, hl.DEFAULT)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(INK, hl.now)).toBeGreaterThanOrEqual(4.5);
  });

  it("is Ink on the yellow", () => {
    expect(MATCH).toContain("bg-hl");
    expect(MATCH).toContain("text-stone-900");
  });
});

describe("the pen", () => {
  it("draws its underline in a colour that is 3:1 or better on white", () => {
    expect(contrast(pen.DEFAULT, "#ffffff")).toBeGreaterThanOrEqual(3);
  });
});

describe("the roles tell each other apart", () => {
  const maroon = /\b(?:bg|text|border|ring)-brand(?!-(?:light|dark|press))\b/;

  it("never draw a selection in maroon", () => {
    for (const selected of [SELECTED, SELECTED_RING, SELECTED_SEGMENT, PILL_SELECTED]) {
      expect(selected).not.toMatch(maroon);
    }
  });

  it("draw a selection as an Ink outline, and here as a stone fill", () => {
    expect(SELECTED).toContain("ring-stone-900");
    expect(SELECTED_RING).toContain("ring-stone-900");
    expect(HERE).toContain("bg-stone-200");
    expect(HERE).not.toMatch(/\b(?:border|ring)-/);
  });

  it("draw a reference as maroon text on white, filled only on hover", () => {
    expect(REFERENCE).toContain("text-brand");
    expect(REFERENCE).toContain("bg-surface");
    expect(REFERENCE).not.toMatch(/(?<!hover:)\bbg-brand\b/);
  });

  it("give yellow and rose to nothing but a match and a pen", () => {
    for (const role of [HERE, SELECTED, SELECTED_RING, SELECTED_SEGMENT, REFERENCE, ...Object.values(TONES)]) {
      expect(role).not.toMatch(/\b(?:hl|pen)\b|-hl-|-pen-|-hl\b|-pen\b/);
    }
  });
});
