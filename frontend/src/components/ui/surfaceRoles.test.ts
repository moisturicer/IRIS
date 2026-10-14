/**
 * Surface roles and the quiet tone (IR-558; 01-design-system.md section 0).
 *
 * One canvas, one content white and one overlay treatment, defined once in
 * the Tailwind theme, so a chip on a card inherits the card's white rather
 * than adding a grey of its own.
 */
import { describe, expect, it } from "vitest";
import resolveConfig from "tailwindcss/resolveConfig";

// @ts-expect-error -- the config is plain JS and ships no declaration file
import tailwindConfig from "../../../tailwind.config.js";

import { PILL_SECONDARY } from "./pillStyles";
import { TONES } from "./statusTones";

const colors = resolveConfig(tailwindConfig).theme.colors as Record<string, unknown>;

describe("surface roles", () => {
  it("defines canvas as stone-50, and surface and overlay as opaque white, once", () => {
    expect(colors.canvas).toBe((colors.stone as Record<string, string>)[50]);
    expect(colors.surface).toBe("#ffffff");
    expect(colors.overlay).toBe("#ffffff");
  });
});

describe("the quiet tone and the secondary pill", () => {
  it("have no fill of their own, so they inherit the surface they sit on", () => {
    expect(TONES.quiet).toMatch(/\bbg-transparent\b/);
    expect(PILL_SECONDARY).toMatch(/\bbg-transparent\b/);
    expect(TONES.quiet).not.toMatch(/\bbg-(?!transparent)/);
    expect(PILL_SECONDARY).not.toMatch(/(?<!hover:)\bbg-(?!transparent)/);
  });

  it("are outlined in stone-300", () => {
    expect(TONES.quiet).toContain("ring-stone-300");
    expect(PILL_SECONDARY).toContain("ring-stone-300");
  });

  it("stay told apart from the other tones by text and outline once quiet loses its fill", () => {
    expect(new Set(Object.values(TONES)).size).toBe(4);
    expect(TONES.quiet).toContain("text-stone-700");
    expect(TONES.active).toContain("ring-brand-200");
    expect(TONES.attention).toMatch(/\bbg-brand\b/);
    expect(TONES.settled).toMatch(/\bbg-stone-900\b/);
  });
});
