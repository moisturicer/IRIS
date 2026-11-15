/**
 * The radius guard (IR-1043): three corner radii and no arbitrary shadow
 * anywhere in the frontend source.
 *
 * It reads every non-test `.ts`, `.tsx` and `.css` file under `src/` as text and
 * fails naming each file and class, the way the palette guard does. This file
 * and `radius.ts` are the only exceptions because their fixtures are deliberately
 * off-scale. No file is allowlisted: IR-1043 migrated every one.
 */
import { describe, expect, it } from "vitest";

import { arbitraryShadowClasses, offRadiusClasses } from "./radius";

const THIS_FILES = new Set(["src/test/radius.test.ts", "src/test/radius.ts"]);
const TEST_FILE = /\.test\.tsx?$/;

const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>("/src/**/*.{ts,tsx,css}", { query: "?raw", import: "default", eager: true }),
  ).map(([path, text]) => [path.replace(/^\//, ""), text]),
);

describe("what counts as an off-scale corner", () => {
  it("catches the default scale on any element, with variants and corners", () => {
    expect(
      offRadiusClasses(
        'className="rounded rounded-sm md:rounded-md rounded-lg rounded-xl rounded-2xl rounded-3xl rounded-t-lg ' +
        'reading-wide:rounded-bl-xl rounded-t border"',
      ),
    ).toEqual([
      "rounded", "rounded-sm", "rounded-md", "rounded-lg", "rounded-xl", "rounded-2xl", "rounded-3xl",
      "rounded-t-lg", "rounded-bl-xl", "rounded-t",
    ]);
  });

  it("catches an arbitrary radius, on a corner too", () => {
    expect(offRadiusClasses('"rounded-[3px] before:rounded-bl-[14px] rounded-[2px]"')).toEqual([
      "rounded-[3px]", "rounded-bl-[14px]", "rounded-[2px]",
    ]);
  });

  it("catches one in a template literal, a cn() call and an @apply", () => {
    expect(offRadiusClasses('`block rounded ${x}` cn(a, "rounded") @apply rounded-bl-xl border')).toEqual([
      "rounded", "rounded-bl-xl",
    ]);
  });

  it("lets the three tokens, a pill and a square corner through", () => {
    expect(
      offRadiusClasses(
        "rounded-control rounded-card rounded-dialog rounded-full rounded-none rounded-t-dialog " +
        "md:rounded-card reading-wide:rounded-none before:rounded-bl-card rounded-tr-none",
      ),
    ).toEqual([]);
  });

  it("does not read comments, a variable or a property", () => {
    expect(
      offRadiusClasses(
        "/** A rounded field with rounded-lg corners. */\n// a rounded card, was rounded-xl\n" +
        "const rounded = Math.floor(x);\nreturn Math.max(1, rounded);\nstyle.rounded;\n" +
        'const url = "http://example.com/rounded";',
      ),
    ).toEqual([]);
  });

  it("does not mistake a word that merely contains rounded", () => {
    expect(offRadiusClasses("grounded-lg surrounded roundedness unrounded-xl")).toEqual([]);
  });
});

describe("what counts as an arbitrary shadow", () => {
  it("catches shadow-[..], with variants, and lets the named shadows through", () => {
    expect(
      arbitraryShadowClasses(
        "shadow-[12px_0_32px_rgb(41_37_36/0.12)] reading-split:shadow-[-12px_0_32px_rgb(0_0_0/0.1)] " +
        "shadow-card shadow-card-md shadow-xl shadow-none",
      ),
    ).toEqual(["shadow-[12px_0_32px_rgb(41_37_36/0.12)]", "shadow-[-12px_0_32px_rgb(0_0_0/0.1)]"]);
  });
});

describe("the radius guard", () => {
  it("reads the whole source tree, not an empty one", () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(100);
    expect(SOURCES["src/components/ui/Modal.tsx"]).toContain("Modal");
    expect(SOURCES["src/index.css"]).toBeDefined();
  });

  it("finds no off-scale corner anywhere in frontend source", () => {
    const offenders = Object.fromEntries(
      Object.entries(SOURCES)
        .filter(([path]) => !THIS_FILES.has(path) && !TEST_FILE.test(path))
        .map(([path, source]) => [path, offRadiusClasses(source)])
        .filter(([, classes]) => classes.length > 0),
    );

    expect(
      offenders,
      "Three corner radii (01-design-system.md, Radius): rounded-control for inputs, buttons and chips, " +
      "rounded-card for cards and panels, rounded-dialog for modals and sheets; rounded-full only for " +
      "pills and avatars. Tailwind's own sizes are not generated.",
    ).toEqual({});
  });

  it("finds no arbitrary shadow anywhere in frontend source", () => {
    const offenders = Object.fromEntries(
      Object.entries(SOURCES)
        .filter(([path]) => !THIS_FILES.has(path) && !TEST_FILE.test(path))
        .map(([path, source]) => [path, arbitraryShadowClasses(source)])
        .filter(([, classes]) => classes.length > 0),
    );

    expect(
      offenders,
      "Shadow is kept for what floats (frontend_redesign_spec §4.12): use shadow-card-md, or none.",
    ).toEqual({});
  });
});
