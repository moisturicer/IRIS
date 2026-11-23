/**
 * The Full Text Rule's guard (IR-1219; DESIGN.md "The eight allowed cuts").
 *
 * Text is never cut off. It reads every non-test `.ts`, `.tsx` and `.css` file
 * under `src/` and fails naming each file and cut class that is not one of the
 * eight cuts DESIGN.md allows. Each allowed file lists exactly the classes it
 * may hold, so a second cut in the same file fails too. Two of the eight have
 * no entry: a review comment's See more cuts in code (`truncateBody`), not
 * with a class, and no table cell cuts a file name today.
 */
import { describe, expect, it } from "vitest";

import { cutClasses } from "./fullText";

const GUARD_FILES = new Set(["src/test/fullText.ts", "src/test/fullTextRule.test.ts"]);
const TEST_FILE = /\.test\.tsx?$/;

/** The allowed cuts, by file: the classes each may hold. */
const ALLOWED: Record<string, string[]> = {
  // An abstract's preview in a list card, which links to the paper.
  "src/components/shared/ResearchCard.tsx": ["line-clamp-4", "line-clamp-3"],
  "src/features/discover/DiscoverResultCard.tsx": ["line-clamp-2"],
  // A call's description on the Calls board, with Show more.
  "src/features/opportunities/CallDetails.tsx": ["line-clamp-2"],
  // Discover's rotating example search.
  "src/features/discover/DiscoverSearchComposer.tsx": ["truncate"],
  // A paper's title in the reading bar, whole on hover, focus and the Overview.
  "src/features/records/paper-view/ReadingHeader.tsx": ["truncate"],
  // A conversation's title in Ask IRIS's list, whole in a tooltip on hover and
  // focus while cut, and in the conversation (IR-1253).
  "src/features/ai/components/ConversationSidebar.tsx": ["truncate"],
  // The signed-in email in the account menu, whole on hover and on Profile (IR-1307).
  "src/components/layout/AccountMenu.tsx": ["truncate"],
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
    expect(found).toEqual(ALLOWED);
  });
});
