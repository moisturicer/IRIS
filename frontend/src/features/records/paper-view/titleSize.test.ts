/** The Overview title's size follows its length (IR-1264). */
import { describe, expect, it } from "vitest";

import { readingVariants } from "../../../../tailwind.config.js";
import { TITLE_LONG_MAX, TITLE_SHORT_MAX, titleSize, titleSizeClasses } from "./titleSize";

const ofLength = (n: number) => "x".repeat(n);

describe("titleSize", () => {
  it("keeps a short title large", () => {
    expect(titleSize("Rainwater Harvesting in Urban Cebu")).toBe("short");
    expect(titleSize(ofLength(TITLE_SHORT_MAX))).toBe("short");
  });

  it("steps a long title down once, and a very long one twice", () => {
    expect(titleSize(ofLength(TITLE_SHORT_MAX + 1))).toBe("long");
    expect(titleSize(ofLength(TITLE_LONG_MAX))).toBe("long");
    expect(titleSize(ofLength(TITLE_LONG_MAX + 1))).toBe("very-long");
  });

  it("measures the title, not the spaces around it", () => {
    expect(titleSize(`   ${ofLength(TITLE_SHORT_MAX)}   `)).toBe("short");
  });

  it("sizes by the Overview's own width, never the window's (the Container Rule)", () => {
    for (const title of [ofLength(10), ofLength(120), ofLength(200)]) {
      const classes = titleSizeClasses(title);
      expect(classes).toMatch(/overview-roomy:text-/);
      expect(classes).not.toMatch(/\b(sm|md|lg|xl):/);
    }
    expect(readingVariants["overview-roomy"]).toBe("@container overview (min-width: 40rem)");
  });

  it("never cuts the title", () => {
    for (const title of [ofLength(10), ofLength(120), ofLength(200)]) {
      expect(titleSizeClasses(title)).not.toMatch(/truncate|line-clamp|text-ellipsis|overflow-hidden/);
    }
  });
});
