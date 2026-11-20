/**
 * The reader reaches a screen only through `lazyReader`'s dynamic import (IR-1247).
 *
 * `PaperPdfReader` carries pdf.js, the largest dependency in the app. A value
 * import of it anywhere else pulls pdf.js into whatever chunk that file is in,
 * and when that file is reachable from every page (as Publish's preview was),
 * every visitor downloads it. A type-only import is erased and stays allowed.
 */
import { describe, expect, it } from "vitest";

const sources = import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;

/** A value import of the PaperPdfReader module, by any path that names it. */
const READER_IMPORT = /^\s*import\s+(?!type\s)[^;]*?from\s+["'][^"']*\/PaperPdfReader["']/m;

describe("the paper reader", () => {
  // `lazyReader` reaches it with a dynamic `import()`, which this does not match:
  // no file may import it statically.
  it("is never imported statically, so pdf.js stays out of the main bundle (IR-1247)", () => {
    const importers = Object.entries(sources)
      .filter(([name]) => !/\.test\.tsx?$/.test(name))
      .filter(([, text]) => READER_IMPORT.test(text))
      .map(([name]) => name.replace("/src/", ""))
      .sort();

    expect(importers).toEqual([]);
  });
});
