/**
 * Field and metadata contrast (IR-1074, D1; audit A11Y-01, A11Y-02, A11Y-10).
 * jsdom cannot measure colour, so the ratios are computed here from the token
 * values, and the source is read as text so a hand-built field cannot keep a
 * Rule Stone outline. The visible check at 1440 and 390 px stays manual.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import resolveConfig from "tailwindcss/resolveConfig";

// @ts-expect-error -- the config is plain JS and ships no declaration file
import tailwindConfig from "../../../tailwind.config.js";

import { CHECKBOX, fieldClasses } from "./fieldClasses";
import { Input } from "./Input";
import { Select } from "./Select";

const theme = resolveConfig(tailwindConfig).theme;
const colors = theme.colors as Record<string, unknown>;
const stone = colors.stone as Record<string, string>;

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

const WHITE = "#ffffff";
const QUIET_INK = "#57534e";

describe("the field tokens (D1)", () => {
  it("names Field Stone #8f8884 and keeps it at least 3:1 on white", () => {
    expect(colors.field).toBe("#8f8884");
    expect(contrast(colors.field as string, WHITE)).toBeGreaterThanOrEqual(3);
  });

  it("is Quiet Ink, stone-600, that placeholder and helper text use, 4.5:1 on every stone surface", () => {
    expect(stone[600]).toBe(QUIET_INK);
    for (const surface of [WHITE, stone[50], stone[100], stone[200]]) {
      expect(contrast(QUIET_INK, surface), surface).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("adds the 14/20 control step for fields and page buttons", () => {
    expect((theme.fontSize as Record<string, unknown>).control).toEqual(["14px", { lineHeight: "20px" }]);
  });
});

describe("the shared field primitives", () => {
  it("outlines Input in Field Stone and sets its placeholder and hint in Quiet Ink", () => {
    render(<Input label="Title" placeholder="A title" hint="Up to 200 characters" />);
    const field = screen.getByRole("textbox", { name: "Title" });
    expect(field).toHaveClass("border-field", "placeholder:text-stone-600", "text-control");
    expect(field).not.toHaveClass("border-stone-300", "placeholder:text-stone-500");
    expect(screen.getByText("Up to 200 characters")).toHaveClass("text-stone-600");
  });

  it("outlines Select in Field Stone and sets its hint in Quiet Ink", () => {
    render(
      <Select label="Area" hint="Pick one">
        <option>One</option>
      </Select>,
    );
    const field = screen.getByRole("combobox", { name: "Area" });
    expect(field).toHaveClass("border-field", "text-control");
    expect(field).not.toHaveClass("border-stone-300");
    expect(screen.getByText("Pick one")).toHaveClass("text-stone-600");
  });

  it("gives hand-built fields and checkboxes the same outline", () => {
    expect(fieldClasses(false)).toContain("border-field");
    expect(fieldClasses(false)).toContain("placeholder:text-stone-600");
    expect(fieldClasses(false)).toContain("text-control");
    expect(fieldClasses(false)).not.toMatch(/border-stone-\d/);
    expect(fieldClasses(true)).toContain("border-brand");
    expect(CHECKBOX).toContain("border-field");
  });
});

const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>("/src/**/*.tsx", { query: "?raw", import: "default", eager: true }),
  ).filter(([path]) => !/\.test\.tsx$/.test(path)),
);

/** Every `<input>`, `<textarea>` and `<select>` opening tag in a source, as one line. */
function fieldTags(source: string): string[] {
  const tags: string[] = [];
  const open = /<(input|textarea|select)\b/g;
  for (let m = open.exec(source); m; m = open.exec(source)) {
    let depth = 0;
    let quote: string | null = null;
    let i = m.index;
    for (; i < source.length; i++) {
      const c = source[i];
      if (quote) {
        if (c === quote && source[i - 1] !== "\\") quote = null;
      } else if (c === '"' || c === "'" || c === "`") quote = c;
      else if (c === "{") depth++;
      else if (c === "}") depth--;
      else if (c === ">" && depth === 0) break;
    }
    tags.push(source.slice(m.index, i + 1).replace(/\s+/g, " "));
  }
  return tags;
}

describe("the field tag scanner", () => {
  it("reads a tag through a className expression that holds a '>'", () => {
    const tags = fieldTags('<input className={a > b ? "x" : "y"} /><p>not me</p><select className="z">');
    expect(tags).toEqual(['<input className={a > b ? "x" : "y"} />', '<select className="z">']);
  });
});

describe("every field in the source (A11Y-01, A11Y-02)", () => {
  it("reads the whole source tree", () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(100);
    expect(Object.values(SOURCES).flatMap(fieldTags).length).toBeGreaterThan(30);
  });

  it("outlines no text field, select or textarea in Rule Stone or lighter", () => {
    const weak = /(?<![\w:-])(?:[\w-]+:)*border-(?:stone|gray)-(?:50|100|200|300)\b/;
    const offenders = Object.entries(SOURCES).flatMap(([path, source]) =>
      fieldTags(source)
        .filter((tag) => !/type="(?:hidden|file|range|radio)"/.test(tag) && weak.test(tag))
        .map((tag) => `${path}: ${tag.slice(0, 120)}`),
    );
    expect(offenders, "Fields are outlined in `border-field` (DESIGN.md D1, IR-1074).").toEqual([]);
  });

  it("sets no placeholder paler than Quiet Ink", () => {
    const pale = /placeholder:text-(?:stone|gray)-(?:300|400|500)\b/;
    const offenders = Object.entries(SOURCES).flatMap(([path, source]) =>
      fieldTags(source).filter((tag) => pale.test(tag)).map((tag) => `${path}: ${tag.slice(0, 120)}`),
    );
    expect(offenders, "Placeholders are `placeholder:text-stone-600` (Quiet Ink).").toEqual([]);
  });
});
