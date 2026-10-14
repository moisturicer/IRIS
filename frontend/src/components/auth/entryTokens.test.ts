/**
 * The entry frame uses only IRIS tokens (IR-535; IR-533 "Tokens and palette").
 *
 * The palette guard (`src/test/palette.test.ts`) catches off-palette hue
 * families. It does not catch what the entry screens actually carried: hex
 * values, arbitrary-value classes such as `text-[9px]` and `bg-[#F3F3F3]`, inline
 * styles, gold as text or as a fill behind text (2.76:1 under white, 2.44:1 on
 * cream) and the cream canvas. This guard reads the entry frame's files as text
 * and fails naming each one.
 *
 * Tickets IR-537 to IR-540 add their screens here as they adopt the frame.
 */
import { describe, expect, it } from "vitest";

const ENTRY_FRAME = [
  "src/components/auth/AuthBrandPanel.tsx",
  "src/components/auth/AuthLayout.tsx",
  "src/features/auth/LoginPage.tsx",
  "src/features/auth/PendingApprovalPage.tsx",
  "src/features/auth/SignupPage.tsx",
];

const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>(["/src/components/auth/*.tsx", "/src/features/auth/*.tsx"], {
      query: "?raw",
      import: "default",
      eager: true,
    }),
  ).map(([path, text]) => [path.replace(/^\//, ""), text]),
);

const RAW_VALUES: Array<[string, RegExp]> = [
  ["hex value", /#[0-9a-fA-F]{3,8}\b/g],
  ["arbitrary-value class", /(?<![\w-])[\w:!/-]*[-/]\[[^\]\s]+\]/g],
  ["inline style", /\bstyle=\{/g],
  ["gold as text or fill", /(?<![\w-])(?:[\w-]+:)*(?:text|bg|from|via|to)-gold(?:-\w+)?\b/g],
  ["cream", /(?<![\w-])(?:[\w-]+:)*[\w-]+-cream\b/g],
];

/** Every raw value in `source`, labelled. */
function rawValues(source: string): string[] {
  return RAW_VALUES.flatMap(([label, pattern]) =>
    [...source.matchAll(pattern)].map((m) => `${label}: ${m[0]}`),
  );
}

describe("what counts as a raw value", () => {
  it("catches hex, arbitrary values, inline styles, gold text and fills, and cream", () => {
    expect(
      rawValues(
        'className="text-[9px] bg-[#F3F3F3] max-w-[400px] border-gold/[0.14] text-gold hover:bg-gold-dark bg-cream" style={{ width: 540 }}',
      ),
    ).toEqual([
      "hex value: #F3F3F3",
      "arbitrary-value class: text-[9px]",
      "arbitrary-value class: bg-[#F3F3F3]",
      "arbitrary-value class: max-w-[400px]",
      "arbitrary-value class: border-gold/[0.14]",
      "inline style: style={",
      "gold as text or fill: text-gold",
      "gold as text or fill: hover:bg-gold-dark",
      "cream: bg-cream",
    ]);
  });

  it("lets tokens through, gold as a border among them", () => {
    expect(rawValues('className="bg-brand text-brand-100 border-t border-gold text-3xs max-w-md size-96 border-white/10"')).toEqual([]);
  });
});

describe("the entry frame", () => {
  it.each(ENTRY_FRAME)("reads %s", (path) => {
    expect(SOURCES[path]).toBeDefined();
  });

  it.each(ENTRY_FRAME)("%s carries no raw value", (path) => {
    expect(rawValues(SOURCES[path] ?? "")).toEqual([]);
  });
});
