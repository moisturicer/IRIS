import postcss from "postcss";
import tailwindcss from "tailwindcss";
import { describe, expect, it } from "vitest";
// @ts-expect-error -- the config is plain JS and ships no declaration file
import config from "../../tailwind.config.js";
import {
  ANSWER_MARKDOWN,
  CHAT_COLUMN,
  OVERVIEW_MARKDOWN,
} from "@/features/ai/components/answerLayout";

// jsdom computes no CSS, so a component test cannot see a `prose` class that
// emits nothing, nor a rule a later modifier overrides (IR-450, IR-451).
// These compile the real config and read the cascade.

const sources = import.meta.glob(
  [
    "/src/features/ai/components/ChatMessageBubble.tsx",
    "/src/features/ai/components/StreamingMessageBubble.tsx",
    "/src/features/records/paper-view/PaperAiOverview.tsx",
  ],
  { query: "?raw", import: "default", eager: true },
) as Record<string, string>;

const layout = import.meta.glob(
  [
    "/src/features/ai/components/ChatMessageList.tsx",
    "/src/features/ai/components/ChatInput.tsx",
  ],
  { query: "?raw", import: "default", eager: true },
) as Record<string, string>;

interface Rule {
  selector: string;
  declarations: Record<string, string>;
}

async function rulesFor(className: string): Promise<Rule[]> {
  const result = await postcss([
    tailwindcss({
      ...config,
      content: [{ raw: `<div class="${className}">`, extension: "html" }],
    }),
  ]).process("@tailwind components; @tailwind utilities;", { from: undefined });

  const rules: Rule[] = [];
  result.root.walkRules((rule) => {
    const declarations: Record<string, string> = {};
    rule.walkDecls((decl) => {
      declarations[decl.prop] = decl.value;
    });
    rules.push({
      selector: rule.selector.replace(/:not\([^)]*\)/g, ""),
      declarations,
    });
  });
  return rules;
}

/** The value that actually applies: the last rule to set it wins, since every
 *  typography selector is wrapped in `:where()` and so has zero specificity. */
function effective(rules: Rule[], element: string, property: string): string | undefined {
  const matching = rules.filter(
    (rule) => rule.selector.includes(`:where(${element})`) && property in rule.declarations,
  );
  return matching[matching.length - 1]?.declarations[property];
}

describe("answer markdown typography", () => {
  it("generates CSS for every element an answer uses", async () => {
    const rules = await rulesFor(ANSWER_MARKDOWN);
    for (const element of ["h2", "ul", "ol", "table", "blockquote", "thead th", "th, td"]) {
      expect(
        rules.some((rule) => rule.selector.includes(`:where(${element})`)),
        `no prose rule for <${element}>`,
      ).toBe(true);
    }
  });

  it("gives h1 and h2 a rule, and leaves h3 without one", async () => {
    const rules = await rulesFor(ANSWER_MARKDOWN);
    expect(effective(rules, "h1, h2", "border-bottom")).toBeDefined();
    expect(effective(rules, "h3", "border-bottom")).toBeUndefined();
  });

  it("keeps headings larger than body text at every level", async () => {
    const rules = await rulesFor(ANSWER_MARKDOWN);
    for (const heading of ["h1", "h2", "h3"]) {
      const size = Number(/([\d.]+)em/.exec(effective(rules, heading, "font-size") ?? "")?.[1]);
      expect(size, `<${heading}> is not larger than body text`).toBeGreaterThan(1);
    }
  });

  it("keeps table text legible, overriding typography's 0.875em", async () => {
    const rules = await rulesFor(ANSWER_MARKDOWN);
    const size = Number(/([\d.]+)em/.exec(effective(rules, "table", "font-size") ?? "")?.[1]);
    expect(size).toBeGreaterThanOrEqual(0.95);
  });

  it("sizes the chat column by the viewport, never a fixed width", () => {
    expect(CHAT_COLUMN).toContain("vw");
    expect(CHAT_COLUMN).not.toMatch(/\d+px/);
    expect(OVERVIEW_MARKDOWN).not.toContain("max-w-none");
  });

  it.each(Object.entries(sources))("%s uses the shared markdown class", (_file, source) => {
    expect(source).toMatch(/\b(ANSWER|OVERVIEW)_MARKDOWN\b/);
    expect(source).not.toContain("[&_ul]");
  });

  it.each(Object.entries(layout))("%s uses the shared column", (_file, source) => {
    expect(source).toContain("CHAT_COLUMN");
    expect(source).not.toContain("max-w-3xl");
  });
});
