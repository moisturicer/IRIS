import { describe, expect, it } from "vitest";
// @ts-expect-error -- the config is plain JS and ships no declaration file
import config from "../../tailwind.config.js";

// Most sizes in this app are written inline as `text-[Npx]`, not taken from the
// named scale, so the two are one ladder that has to move together. Raising the
// scale alone leaves three quarters of the app behind (IR-452).

// 18px and up is heading territory, on Tailwind's own xl/2xl ladder.
const BODY = { min: 11, max: 17 };

const sources = import.meta.glob("/src/**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function inlineSizes(): Map<number, string[]> {
  const found = new Map<number, string[]>();
  for (const [file, source] of Object.entries(sources)) {
    if (file.includes(".test.")) continue;
    for (const match of source.matchAll(/text-\[(\d+)px\]/g)) {
      const size = Number(match[1]);
      found.set(size, [...(found.get(size) ?? []), file]);
    }
  }
  return found;
}

type FontSize = [string, { lineHeight: string }];

/**
 * The type roles (IR-405; spec §4.12). Named for what the text is rather than
 * how big it is, so a screen picks `text-title` for a dialog title and the
 * size follows. They sit beside the size ladder, not on it: two of them are
 * heading sizes, which the ladder deliberately stops short of.
 */
const ROLES: Record<string, [number, number]> = {
  display: [28, 34],
  title:   [20, 28],
  heading: [16, 24],
  body:    [15, 24],
  small:   [13, 20],
  label:   [12, 16],
};

function px(value: string): number {
  return Number(value.replace("px", ""));
}

function scaleSizes(): number[] {
  const scale = config.theme.extend.fontSize as Record<string, FontSize>;
  return Object.entries(scale)
    .filter(([name]) => !(name in ROLES))
    .map(([, [size]]) => px(size));
}

describe("type scale", () => {
  it("covers every body size written inline in a component", () => {
    const named = scaleSizes();
    const orphans = [...inlineSizes().entries()]
      .filter(([size]) => size >= BODY.min && size <= BODY.max)
      .filter(([size]) => !named.includes(size))
      .map(([size, files]) => `${size}px (${files.length} files, e.g. ${files[0]})`);

    // Raising the scale means sweeping the inline sizes in the same commit.
    expect(orphans, `inline body sizes with no step on the scale:\n${orphans.join("\n")}`).toEqual(
      [],
    );
  });

  it("keeps the scale a contiguous ladder with no gaps", () => {
    const sorted = [...scaleSizes()].sort((a, b) => a - b);
    for (let i = 1; i < sorted.length; i += 1) {
      expect(sorted[i] - sorted[i - 1], `gap between ${sorted[i - 1]}px and ${sorted[i]}px`).toBe(1);
    }
  });

  it("defines each type role at the size and leading the spec gives it", () => {
    const scale = config.theme.extend.fontSize as Record<string, FontSize>;
    const defined = Object.fromEntries(
      Object.keys(ROLES).map((role) => {
        const entry = scale[role];
        return [role, entry ? [px(entry[0]), px(entry[1].lineHeight)] : undefined];
      }),
    );

    expect(defined).toEqual(ROLES);
  });

  it("sets Discover titles in the face the paper view gives a title", () => {
    // Since IR-407 (F2) Discover draws no title of its own: its page head is
    // `PageHeader` and its results are `ResearchCard`, so the guard reads those.
    for (const file of [
      "/src/components/shared/ResearchCard.tsx",
      "/src/components/layout/PageHeader.tsx",
    ]) {
      // Only EB Garamond 600 is loaded, so a title is semibold, never bold.
      expect(sources[file], `${file} has no display-face title`).toMatch(
        /font-display[^"]*font-semibold/,
      );
    }
  });
});
