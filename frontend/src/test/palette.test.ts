/**
 * The palette guard (IR-358, closed by IR-366): no off-palette colour class
 * anywhere in the frontend source.
 *
 * It reads every `.ts`, `.tsx` and `.css` file under `src/` as text and fails
 * naming each file and class. This test file is the only exception because its
 * fixtures are deliberately off-palette.
 */
import { describe, expect, it } from "vitest";

import { offGreyClasses, offPaletteClasses, retiredTintClasses, seeThroughWhiteClasses, strayHexes } from "./palette";

const THIS_FILE = "src/test/palette.test.ts";

/**
 * The retired-tint and stray-hex guards read shipped source only: a test names
 * a retired class or hex on purpose, as a fixture or to assert it is gone.
 */
const TEST_FILE = /\.test\.tsx?$/;

/** Every source file, keyed `src/...`, read as text. */
const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>("/src/**/*.{ts,tsx,css}", {
      query: "?raw",
      import: "default",
      eager: true,
    }),
  ).map(([path, text]) => [path.replace(/^\//, ""), text]),
);

describe("what counts as off-palette", () => {
  it("catches a hue family on any colour utility, with variants and opacity", () => {
    expect(
      offPaletteClasses(
        'className="bg-red-50 hover:text-emerald-700 md:border-t-amber-200 ring-sky-500/40 !from-violet-950"',
      ),
    ).toEqual([
      "bg-red-50", "text-emerald-700", "border-t-amber-200", "ring-sky-500", "from-violet-950",
    ]);
  });

  it("catches brand-400 to brand-600, the bright reds, and no other brand shade", () => {
    expect(
      offPaletteClasses("bg-brand-400 text-brand-500 ring-brand-600 bg-brand-50 ring-brand-200 text-brand-700"),
    ).toEqual(["bg-brand-400", "text-brand-500", "ring-brand-600"]);
  });

  it("lets white, black, grey and maroon through", () => {
    expect(
      offPaletteClasses(
        "bg-white text-black bg-stone-100 text-stone-700 border-gray-200 text-slate-500 " +
        "bg-brand text-brand-light bg-brand-dark bg-brand-50 ring-brand/40",
      ),
    ).toEqual([]);
  });

  it("does not mistake a word that merely contains a hue for a class", () => {
    expect(offPaletteClasses("redirect-500 skyline-100 prefix-bg-red-500 bg-red-5000")).toEqual([]);
  });
});

describe("what counts as a second grey or a see-through white (IR-558)", () => {
  it("catches gray and slate on any colour utility, with variants and opacity", () => {
    expect(
      offGreyClasses('className="bg-gray-50 hover:text-slate-700 md:border-t-gray-200 ring-slate-500/40"'),
    ).toEqual(["bg-gray-50", "text-slate-700", "border-t-gray-200", "ring-slate-500"]);
  });

  it("lets stone through, and a word that merely contains gray", () => {
    expect(offGreyClasses("bg-stone-50 text-stone-700 grayscale -webkit-grayscale bg-gray-5000")).toEqual([]);
  });

  it("catches a white background with any opacity below full", () => {
    expect(
      seeThroughWhiteClasses("bg-white/90 backdrop-blur hover:bg-white/[0.6] md:bg-white/60 !bg-white/5"),
    ).toEqual(["bg-white/90", "bg-white/[0.6]", "bg-white/60", "bg-white/5"]);
  });

  it("lets an opaque white, a text or border white and a see-through grey through", () => {
    expect(
      seeThroughWhiteClasses("bg-white bg-white/100 bg-surface bg-overlay text-white/70 border-white/20 bg-stone-50/80"),
    ).toEqual([]);
  });
});

describe("what counts as a retired highlight tint (IR-1097, D6)", () => {
  it("catches Maroon Wash, its pinker neighbours, gold and cream on any colour utility", () => {
    expect(
      retiredTintClasses(
        'className="bg-brand-50 hover:bg-brand-100 ring-brand-200 md:border-t-gold bg-brand-50/40 text-gold-dark bg-cream"',
      ),
    ).toEqual(["bg-brand-50", "bg-brand-100", "ring-brand-200", "border-t-gold", "text-gold-dark", "bg-cream"]);
  });

  it("catches maroon at 5 or 10 percent, the wash made by opacity, and lets stronger focus rings through", () => {
    expect(retiredTintClasses("bg-brand/5 bg-brand/10 border-brand/10 ring-brand/40 bg-brand/15 hover:bg-brand/30")).toEqual([
      "bg-brand/5", "bg-brand/10", "border-brand/10",
    ]);
  });

  it("lets maroon, its darker shades, the new highlight tokens and a word containing a tint through", () => {
    expect(
      retiredTintClasses(
        "bg-brand text-brand-light bg-brand-dark bg-brand-press ring-brand/40 bg-brand-700 " +
        "bg-hl bg-hl-now bg-pen-wash bg-pen-now decoration-pen bg-stone-200 goldfish-100 bg-brand-500x",
      ),
    ).toEqual([]);
  });

  it("catches the loose hexes the audit found, and the wash, in any case", () => {
    expect(strayHexes("a { color: #FBE4E4; } b { fill: #fcfcfb } c { x: #5a0c0f; y: #fdf2f2 }")).toEqual([
      "#fbe4e4", "#fcfcfb", "#5a0c0f", "#fdf2f2",
    ]);
  });

  it("lets the thread rose, the highlights and a longer hex through", () => {
    expect(strayHexes("#f9b8b9 #f7e08f #f2c94c #b4474b #fbeaea #f5d5d6 #fdf2f2a0")).toEqual([]);
  });
});

describe("the palette guard", () => {
  it("reads the whole source tree, not an empty one", () => {
    // A broken glob would make the guards below pass by reading nothing.
    expect(Object.keys(SOURCES).length).toBeGreaterThan(100);
    expect(SOURCES["src/components/shared/StatusBadge.tsx"]).toContain("StatusBadge");
    expect(SOURCES["src/index.css"]).toBeDefined();
  });

  it("finds no off-palette colour anywhere in frontend source", () => {
    const offenders = Object.fromEntries(
      Object.entries(SOURCES)
        .filter(([path]) => path !== THIS_FILE)
        .map(([path, source]) => [path, offPaletteClasses(source)])
        .filter(([, classes]) => classes.length > 0),
    );

    expect(
      offenders,
      "Off-palette colours (01-design-system.md section 0). Use stone, brand or a TONES entry " +
      "from components/ui/statusTones.ts.",
    ).toEqual({});
  });

  it("finds no second grey anywhere in frontend source", () => {
    const offenders = Object.fromEntries(
      Object.entries(SOURCES)
        .filter(([path]) => path !== THIS_FILE)
        .map(([path, source]) => [path, offGreyClasses(source)])
        .filter(([, classes]) => classes.length > 0),
    );

    expect(
      offenders,
      "gray and slate are a second grey beside stone (01-design-system.md section 0). Write stone.",
    ).toEqual({});
  });

  it("finds no retired highlight tint anywhere in frontend source", () => {
    const offenders = Object.fromEntries(
      Object.entries(SOURCES)
        .filter(([path]) => path !== THIS_FILE && !TEST_FILE.test(path))
        .map(([path, source]) => [path, retiredTintClasses(source)])
        .filter(([, classes]) => classes.length > 0),
    );

    expect(
      offenders,
      "Maroon Wash, brand-100, brand-200, gold and cream are retired (DESIGN.md, D6). Pick the role: " +
      "here, selected, reference, notice or status from components/ui/highlightRoles.ts, or the " +
      "match and pen tokens (hl, hl-now, pen, pen-wash, pen-now).",
    ).toEqual({});
  });

  it("finds no stray or retired hex anywhere in frontend source", () => {
    const offenders = Object.fromEntries(
      Object.entries(SOURCES)
        .filter(([path]) => path !== THIS_FILE && !TEST_FILE.test(path))
        .map(([path, source]) => [path, strayHexes(source)])
        .filter(([, hexes]) => hexes.length > 0),
    );

    expect(
      offenders,
      "#fbe4e4, #fcfcfb, #5a0c0f and the wash #fdf2f2 are loose or retired. Use a token from " +
      "tailwind.config.js (brand-press for a pressed filled button).",
    ).toEqual({});
  });

  it("finds no see-through white background anywhere in frontend source", () => {
    const offenders = Object.fromEntries(
      Object.entries(SOURCES)
        .filter(([path]) => path !== THIS_FILE)
        .map(([path, source]) => [path, seeThroughWhiteClasses(source)])
        .filter(([, classes]) => classes.length > 0),
    );

    expect(
      offenders,
      "A see-through white shows whatever is behind it. Use bg-surface for content and bg-overlay " +
      "for floating controls (01-design-system.md section 0).",
    ).toEqual({});
  });
});
