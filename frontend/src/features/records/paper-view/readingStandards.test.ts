/**
 * The reading surfaces' control standard, held by the build (IR-569;
 * 01-design-system.md section 0, "Reading controls").
 *
 * Like the palette guard (`test/palette.test.ts`), each rule has a shrinking
 * allowlist: a file already breaking it is listed so the rule can start now,
 * and the list only gets shorter. Remove a name when its file is converted.
 * Adding one needs a reason in the PR.
 */
import { describe, expect, it } from "vitest";

import {
  CONTROL_BASE,
  CONTROL_FILLED,
  CONTROL_ON,
  CONTROL_OUTLINE,
  CONTROL_SHAPE,
  CONTROL_SIZE,
  CONTROL_SQUARE,
} from "./controls";

const sources = import.meta.glob("./*.tsx", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;
const files = Object.entries(sources).filter(([name]) => !name.endsWith(".test.tsx"));

/** Files in this folder that contain a match for `pattern`, by name. */
function offenders(pattern: RegExp): string[] {
  return files
    .filter(([, text]) => pattern.test(text))
    .map(([name]) => name.replace("./", ""))
    .sort();
}

describe("the control scale", () => {
  it("is 44px on touch and 36px beside a pointer, whichever way it is written", () => {
    expect(CONTROL_SIZE).toBe("min-h-11 reading-split:min-h-9");
    expect(CONTROL_SQUARE).toBe("w-11 h-11 reading-split:w-9 reading-split:h-9");
    expect(CONTROL_SHAPE).toBe("rounded-lg");
    expect(CONTROL_BASE).toContain(CONTROL_SIZE);
    expect(CONTROL_BASE).toContain(CONTROL_SHAPE);
  });

  it("has one filled state, one tint and one outline, each with a border so they size alike", () => {
    for (const state of [CONTROL_FILLED, CONTROL_ON, CONTROL_OUTLINE]) {
      expect(state).toMatch(/\bborder\b/);
    }
  });
});

describe("controls in the reading surfaces", () => {
  it("take their size from the reading container, not the window", () => {
    // `lg:` is the window; a control beside the sidebar or Ask IRIS must follow
    // the room it has. No file is excused.
    expect(offenders(/\blg:(min-h-|h-|w-)/)).toEqual([]);
  });

  it("are rounded-lg, not rounded-md", () => {
    // ReadingHeader's section thumb sits one radius step inside its track on
    // purpose, so the two are concentric. The others are older.
    expect(offenders(/\brounded-md\b/)).toEqual([
      "PaperDocuments.tsx",
      "ReadingHeader.tsx",
      "ReviewRoutingTracker.tsx",
    ]);
  });

  it("use the type scale's names, not a pixel size, for text", () => {
    expect(offenders(/\btext-\[\d+px\]/)).toEqual([
      "AddReviewerDialog.tsx",
      "DecisionDialog.tsx",
      "NewVersionDialog.tsx",
      "OfficeReviewDialog.tsx",
      "RequestRevisionDialog.tsx",
      "RouteDialog.tsx",
    ]);
  });
});
