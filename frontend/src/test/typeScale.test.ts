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

function scaleSizes(): number[] {
  const scale = config.theme.extend.fontSize as Record<string, [string, unknown]>;
  return Object.values(scale).map(([size]) => Number(size.replace("px", "")));
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

  it("sets Discover titles in the face the paper view gives a title", () => {
    for (const file of [
      "/src/features/discover/DiscoverRecordCard.tsx",
      "/src/features/discover/DiscoverPage.tsx",
    ]) {
      // Only EB Garamond 600 is loaded, so a title is semibold, never bold.
      expect(sources[file], `${file} has no display-face title`).toMatch(
        /font-display[^"]*font-semibold/,
      );
    }
  });
});
