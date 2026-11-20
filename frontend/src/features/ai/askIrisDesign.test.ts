import { describe, expect, it } from "vitest";

import { ANSWER_TEXT } from "./components/answerLayout";

// IR-1235: Ask IRIS draws on the design system's type roles and one outline icon
// set. jsdom computes no CSS, so what a component renders cannot show a size or
// an icon font; these read the source of the feature instead and fail on the
// two things the ticket removes. Visual size and contrast stay a manual check
// against the prototype.

const modules = import.meta.glob(
  ["/src/features/ai/**/*.{ts,tsx}", "!/src/features/ai/**/*.test.{ts,tsx}"],
  { query: "?raw", import: "default", eager: true },
) as Record<string, string>;

const files = Object.entries(modules);

/** Tailwind size utilities the ticket removes, with any variant prefix in front. */
const REMOVED_SIZES = /\btext-(xs|sm|base|xl|2xl|3xl|2xs|3xs|label|display)\b/;
/** An arbitrary font size under the 13 px floor. */
const ARBITRARY_SIZE = /\btext-\[(\d+(?:\.\d+)?)px\]/g;

describe("Ask IRIS design (IR-1235)", () => {
  it("scans the feature's sources", () => {
    expect(files.length).toBeGreaterThan(20);
  });

  it.each(files)("%s uses no Font Awesome icon", (_file, source) => {
    expect(source).not.toMatch(/\bfa-[a-z]/);
    expect(source).not.toMatch(/<i\b/);
  });

  it.each(files)("%s uses only the type roles, none below 13 px", (_file, source) => {
    expect(source).not.toMatch(REMOVED_SIZES);
    for (const [, px] of source.matchAll(ARBITRARY_SIZE)) {
      expect(Number(px), `text-[${px}px] is under the 13 px floor`).toBeGreaterThanOrEqual(13);
    }
  });

  it("sets an answer's text in the reading role, 16 px on a 1.75 line, wherever the thread shows one", () => {
    expect(ANSWER_TEXT).toBe("text-md leading-[1.75]");
    for (const name of ["ChatMessageBubble", "StreamingMessageBubble", "RuntimeReader"]) {
      const source = modules[`/src/features/ai/components/${name}.tsx`];
      // Once in the import, once where the answer is drawn.
      expect(source.match(/\bANSWER_TEXT\b/g)?.length, name).toBeGreaterThanOrEqual(2);
    }
  });

  it("leaves the measure to the column: no `ch` cap on text (DESIGN.md, the Flush Column Rule)", () => {
    expect(ANSWER_TEXT).not.toMatch(/max-w/);
    for (const [file, source] of files) {
      expect(source, file).not.toMatch(/\bmax-w-\[\d+ch\]/);
    }
  });
});
