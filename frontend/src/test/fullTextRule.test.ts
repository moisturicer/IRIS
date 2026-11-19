/**
 * The Full Text Rule's guard (IR-1219; DESIGN.md "The five allowed cuts").
 *
 * Text is never cut off. It reads every non-test `.ts`, `.tsx` and `.css` file
 * under `src/` and fails naming each file and cut class that is not one of the
 * five cuts DESIGN.md allows. Each allowed file lists exactly the classes it
 * may hold, so a second cut in the same file fails too. A review comment's
 * See more cuts in code (`truncateBody`), not with a class, so it has no entry.
 */
import { describe, expect, it } from "vitest";

import { cutClasses } from "./fullText";

const GUARD_FILES = new Set(["src/test/fullText.ts", "src/test/fullTextRule.test.ts"]);
const TEST_FILE = /\.test\.tsx?$/;

/** The allowed cuts, by file: the classes each may hold, and which cut they are. */
const ALLOWED: Record<string, { classes: string[]; cut: string }> = {
  "src/components/shared/ResearchCard.tsx": {
    classes: ["line-clamp-4", "line-clamp-3"],
    cut: "an abstract's preview in a list card, which links to the paper",
  },
  "src/features/discover/DiscoverResultCard.tsx": {
    classes: ["line-clamp-2"],
    cut: "an abstract's preview in a list card, which links to the paper",
  },
  "src/features/opportunities/CallDetails.tsx": {
    classes: ["line-clamp-2"],
    cut: "a call's description on the Calls board, with Show more",
  },
  "src/features/discover/DiscoverSearchComposer.tsx": {
    classes: ["truncate"],
    cut: "Discover's rotating example search",
  },
};

const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>("/src/**/*.{ts,tsx,css}", { query: "?raw", import: "default", eager: true }),
  ).map(([path, text]) => [path.replace(/^\//, ""), text]),
);

describe("what counts as a cut", () => {
  it("catches truncate, text-ellipsis and a line clamp, with variants", () => {
    expect(cutClasses('className="block truncate md:line-clamp-2 text-ellipsis line-clamp-[7]"')).toEqual([
      "truncate", "line-clamp-2", "text-ellipsis", "line-clamp-[7]",
    ]);
  });

  it("lets a removed clamp, a name and a comment through", () => {
    expect(
      cutClasses(
        '/** was truncate */ // line-clamp-2 before\n' +
        'const { truncated } = truncateBody(body); "md:line-clamp-none"',
      ),
    ).toEqual([]);
  });
});

describe("the Full Text Rule", () => {
  it("reads the frontend source", () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(100);
  });

  it("cuts text only where DESIGN.md allows it", () => {
    const found: Record<string, string[]> = {};
    for (const [path, text] of Object.entries(SOURCES)) {
      if (GUARD_FILES.has(path) || TEST_FILE.test(path)) continue;
      const cuts = cutClasses(text);
      if (cuts.length) found[path] = cuts;
    }
    const allowed = Object.fromEntries(Object.entries(ALLOWED).map(([path, { classes }]) => [path, classes]));
    expect(found).toEqual(allowed);
  });
});
