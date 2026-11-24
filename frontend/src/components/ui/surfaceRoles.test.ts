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
  // IR-1132: every page sits on white, as Discover does. The ground is still
  // its own role, so a screen asks for `canvas` and the ground can change
  // again in one place, but it is no longer a grey of its own.
  it("defines canvas, surface and overlay as opaque white, once", () => {
    expect(colors.canvas).toBe("#ffffff");
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

  // IR-1290: five tones, each told apart by its text and outline colour.
  it("stay told apart from the other tones by text and outline once quiet loses its fill", () => {
    expect(new Set(Object.values(TONES)).size).toBe(5);
    expect(TONES.quiet).toContain("text-stone-700");
    expect(TONES.active).toContain("text-review");
    expect(TONES.active).toContain("ring-review-line");
    expect(TONES.cleared).toContain("text-cleared");
    expect(TONES.cleared).toContain("ring-cleared-line");
    expect(TONES.attention).toContain("text-brand");
    expect(TONES.attention).toMatch(/\bring-brand\b/);
    expect(TONES.settled).toContain("ring-stone-900");
  });

  // IR-1290 replaces IR-1097's "only Attention is filled": a status is always
  // a white chip with its tone in the text and the outline. A solid maroon fill
  // is the one action to take next, so no status may wear it, Attention
  // included, and a status never reads as a button, a selection or a here by
  // its fill alone.
  it("fill no tone", () => {
    for (const [tone, classes] of Object.entries(TONES)) {
      expect(classes, tone).not.toMatch(/(?<![:\w-])bg-(?!transparent|surface\b|white\b)/);
    }
  });
});

describe("the highlight tokens (IR-1097, D6)", () => {
  it("define the match yellow and the current match, with the prototype's values", () => {
    expect(colors.hl).toEqual({ DEFAULT: "#F7E08F", now: "#F2C94C" });
  });

  it("define the reviewer's pen: underline, fill and the open thread's passage", () => {
    expect(colors.pen).toEqual({ DEFAULT: "#B4474B", wash: "#FBEAEA", now: "#F5D5D6" });
  });

  // IR-1290: the two status hues, with the values the contrast figures in
  // DESIGN.md were computed from.
  it("define the cleared green and the review amber: text, outline and wash", () => {
    expect(colors.cleared).toEqual({ DEFAULT: "#1E6B3F", line: "#3F8A5A", wash: "#EAF3EC" });
    expect(colors.review).toEqual({ DEFAULT: "#8A5300", line: "#B07A1E", wash: "#FBF0DA" });
  });

  it("define the pressed filled button as brand-press, and drop gold and cream", () => {
    expect((colors.brand as Record<string, string>).press).toBe("#5A0C0F");
    expect(colors.gold).toBeUndefined();
    expect(colors.cream).toBeUndefined();
  });
});
