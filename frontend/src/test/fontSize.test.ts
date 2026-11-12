/**
 * The font-size guard (IR-1037): no new arbitrary font size anywhere in the
 * frontend source, and nothing under 12 px.
 *
 * Sizes come from the type roles (`text-display`, `text-title`, `text-heading`,
 * `text-body`, `text-small`, `text-label`). The palette guard stops an
 * off-palette colour; this stops a hardcoded size.
 *
 * Like the palette guard, it has a shrinking allowance: the sizes already in the
 * code are recorded per file in `fontSizeAllowance.ts`, so the rule can start
 * now and the number only goes down. Unlike the palette guard it counts, because
 * a file is migrated over several changes and each one must be locked in.
 *
 * `features/records/paper-view/readingStandards.test.ts` holds an older, coarser
 * version of this rule for six dialog files (name only, no count). The two agree
 * today. When those dialogs are migrated (IR-1042), remove them from both.
 */
import { describe, expect, it } from "vitest";

import {
  arbitraryFontSizes,
  isBelowFloor,
  MIN_TEXT_PX,
  suggestedRole,
  type ArbitrarySize,
} from "./fontSize";
import { FONT_SIZE_ALLOWANCE, SUB_12PX_ALLOWANCE } from "./fontSizeAllowance";

/** The guard's own files hold examples of what it rejects. */
const GUARD_FILES = new Set([
  "src/test/fontSize.ts",
  "src/test/fontSize.test.ts",
  "src/test/fontSizeAllowance.ts",
]);

/** Every non-test source file, keyed `src/...`, read as text. */
const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>("/src/**/*.{ts,tsx}", {
      query: "?raw",
      import: "default",
      eager: true,
    }),
  )
    .map(([path, text]) => [path.replace(/^\//, ""), text] as const)
    .filter(([path]) => !/\.test\.tsx?$/.test(path) && !GUARD_FILES.has(path)),
);

describe("what counts as an arbitrary font size", () => {
  it("catches a px or rem size, with variants, in the order written", () => {
    expect(
      arbitraryFontSizes('className="text-[13px] md:text-[14px] !text-[0.75rem] hover:text-[1.25rem]"'),
    ).toEqual([
      { cls: "text-[13px]", px: 13 },
      { cls: "text-[14px]", px: 14 },
      { cls: "text-[0.75rem]", px: 12 },
      { cls: "text-[1.25rem]", px: 20 },
    ]);
  });

  it("reads a fractional size", () => {
    expect(arbitraryFontSizes("text-[11.5px]")).toEqual([{ cls: "text-[11.5px]", px: 11.5 }]);
  });

  it("lets the type roles, the named ladder and colour or length values through", () => {
    expect(
      arbitraryFontSizes(
        "text-label text-small text-body text-heading text-title text-display text-xs text-sm text-3xl " +
          "text-[#6B0F12] text-[var(--x)] text-brand text-stone-700",
      ),
    ).toEqual([]);
  });

  it("does not mistake a longer class name for a font size", () => {
    expect(arbitraryFontSizes("context-text-[13px] prefix_text-[13px]")).toEqual([]);
  });

  it("puts the floor at 12 px", () => {
    expect(MIN_TEXT_PX).toBe(12);
    expect(isBelowFloor({ cls: "text-[11px]", px: 11 })).toBe(true);
    expect(isBelowFloor({ cls: "text-[11.9px]", px: 11.9 })).toBe(true);
    expect(isBelowFloor({ cls: "text-[12px]", px: 12 })).toBe(false);
    expect(isBelowFloor({ cls: "text-[0.7rem]", px: 11.2 })).toBe(true);
  });

  it("names a role for every size, 14 px as body", () => {
    expect(suggestedRole(9)).toContain("text-label");
    expect(suggestedRole(12)).toBe("text-label");
    expect(suggestedRole(13)).toBe("text-small");
    expect(suggestedRole(14)).toBe("text-body");
    expect(suggestedRole(15)).toBe("text-body");
    expect(suggestedRole(16)).toBe("text-heading");
    expect(suggestedRole(20)).toBe("text-title");
    expect(suggestedRole(32)).toBe("text-display");
  });
});

describe("the font-size guard", () => {
  it("reads the whole source tree, not an empty one", () => {
    // A broken glob would make the guards below pass by reading nothing.
    expect(Object.keys(SOURCES).length).toBeGreaterThan(100);
    expect(SOURCES["src/components/shared/StatusBadge.tsx"]).toContain("StatusBadge");
    expect(Object.keys(SOURCES).some((path) => path.endsWith(".test.tsx"))).toBe(false);
  });

  /**
   * Each file against its allowance: more is a new size, fewer is a file to
   * lower. A file or an entry the tree no longer has is reported too, so the
   * allowance cannot outlive what it describes.
   */
  function problems(
    pick: (size: ArbitrarySize) => boolean,
    allowance: Record<string, number>,
    advice: string,
  ): string[] {
    const found: Record<string, ArbitrarySize[]> = {};
    for (const [path, source] of Object.entries(SOURCES)) {
      const sizes = arbitraryFontSizes(source).filter(pick);
      if (sizes.length > 0) found[path] = sizes;
    }
    const lines: string[] = [];
    for (const path of Object.keys({ ...found, ...allowance }).sort()) {
      const sizes = found[path] ?? [];
      const allowed = allowance[path] ?? 0;
      if (path in allowance && !(path in SOURCES)) {
        lines.push(`${path}: no such file, remove its entry from src/test/fontSizeAllowance.ts`);
      } else if (sizes.length > allowed) {
        const where = sizes.map((s) => `${s.cls} -> ${suggestedRole(s.px)}`).join(", ");
        lines.push(`${path}: ${sizes.length} found, ${allowed} allowed. ${advice} (${where})`);
      } else if (sizes.length < allowed) {
        const to = sizes.length === 0 ? "remove its entry" : `lower it to ${sizes.length}`;
        lines.push(
          `${path}: ${sizes.length} found, ${allowed} allowed. Good, now ${to} in src/test/fontSizeAllowance.ts`,
        );
      }
    }
    return lines;
  }

  it("finds no arbitrary font size beyond the allowance", () => {
    expect(
      problems(
        (size) => !isBelowFloor(size),
        FONT_SIZE_ALLOWANCE,
        "Use a type role (01-design-system.md section 0) instead of a pixel size.",
      ),
    ).toEqual([]);
  });

  it("finds no text under 12 px beyond the allowance", () => {
    expect(
      problems(
        isBelowFloor,
        SUB_12PX_ALLOWANCE,
        `Nothing renders under ${MIN_TEXT_PX} px (frontend_redesign_spec section 4.12). Use text-label.`,
      ),
    ).toEqual([]);
  });
});
