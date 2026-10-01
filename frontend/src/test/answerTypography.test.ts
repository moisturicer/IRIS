import postcss from "postcss";
import tailwindcss from "tailwindcss";
import { describe, expect, it } from "vitest";
// @ts-expect-error -- the config is plain JS and ships no declaration file
import config from "../../tailwind.config.js";
import { ANSWER_MARKDOWN } from "@/features/ai/components/markdownStyle";

// jsdom computes no CSS, so a component test cannot see a `prose` class that
// emits nothing. This compiles the class through the real Tailwind config
// instead (IR-450).

const sources = import.meta.glob(
  [
    "/src/features/ai/components/ChatMessageBubble.tsx",
    "/src/features/ai/components/StreamingMessageBubble.tsx",
    "/src/features/records/paper-view/PaperAiOverview.tsx",
  ],
  { query: "?raw", import: "default", eager: true },
) as Record<string, string>;

async function compile(markup: string): Promise<string> {
  const result = await postcss([
    tailwindcss({ ...config, content: [{ raw: markup, extension: "html" }] }),
  ]).process("@tailwind components; @tailwind utilities;", { from: undefined });
  return result.css;
}

describe("answer markdown typography", () => {
  it("generates CSS for the prose classes the answer surfaces use", async () => {
    const css = await compile(`<div class="${ANSWER_MARKDOWN}"></div>`);
    for (const selector of [
      ":where(h2)",
      ":where(ul)",
      ":where(ol)",
      ":where(table)",
      ":where(blockquote)",
      ":where(thead th)",
      ":where(th, td)",
    ]) {
      expect(css, `no prose rule for ${selector}`).toContain(`.prose ${selector}`);
    }
  });

  it.each(Object.entries(sources))("%s uses the shared class, not its own", (_file, source) => {
    expect(source).toContain("ANSWER_MARKDOWN");
    expect(source).not.toContain("[&_ul]");
  });
});
