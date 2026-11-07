/**
 * Hostile input to a quoted Passage (IR-917).
 *
 * A passage is text lifted from a manuscript, so its author controls it.
 * `PassageQuote` writes KaTeX output with `dangerouslySetInnerHTML`, which makes
 * it the one surface where a mistake becomes script execution. Everything
 * outside a `$$...$$` span is a React text node.
 */
import katex from "katex";
import { afterEach, describe, expect, it, vi } from "vitest";

import { expectInert } from "@/test/hostile";
import { renderScreen } from "@/test/render";

import { PassageQuote } from "./PassageQuote";

declare global {
  interface Window {
    __pwned?: unknown;
  }
}

afterEach(() => {
  delete window.__pwned;
});

function render(text: string) {
  return renderScreen(<PassageQuote text={text} />).container;
}

describe("markup in a passage's prose", () => {
  it.each([
    ["a script", "<script>window.__pwned = 1</script>"],
    ["an image handler", '<img src=x onerror="window.__pwned = 1">'],
    ["an svg handler", '<svg onload="window.__pwned = 1"></svg>'],
    ["an anchor", '<a href="javascript:window.__pwned=1">open</a>'],
    ["an iframe", '<iframe srcdoc="<script>1</script>"></iframe>'],
  ])("shows %s as literal text, not an element", (_label, html) => {
    const container = render(`Quote ${html} end`);

    expectInert(container);
    expect(container.querySelector("blockquote")?.textContent).toBe(`Quote ${html} end`);
    expect(window.__pwned).toBeUndefined();
  });

  it("does not turn markdown link syntax into a link (passages are not run through Markdown)", () => {
    const container = render("[click](javascript:window.__pwned=1) and https://evil.test");

    expectInert(container);
    expect(container.querySelector("a")).toBeNull();
  });

  it("keeps hostile text in the title attribute as an attribute value", () => {
    const container = render('"><img src=x onerror="window.__pwned=1">');

    expectInert(container);
    expect(container.querySelector("blockquote")?.getAttribute("title")).toBe('"><img src=x onerror="window.__pwned=1">');
  });
});

describe("a hostile formula in a passage", () => {
  const inert = (container: HTMLElement) => expectInert(container, { allowTags: ["svg"] });

  it.each([
    ["\\href to javascript:", "\\href{javascript:window.__pwned=1}{click}"],
    ["\\url to javascript:", "\\url{javascript:window.__pwned=1}"],
    ["\\href to data:", "\\href{data:text/html;base64,PHNjcmlwdD4xPC9zY3JpcHQ+}{click}"],
    ["\\href to https", "\\href{https://evil.test}{click}"],
    ["\\htmlClass", "\\htmlClass{admin}{y}"],
    ["\\htmlId", "\\htmlId{root}{y}"],
    ["\\htmlStyle", "\\htmlStyle{position:fixed;inset:0}{y}"],
    ["\\htmlData", "\\htmlData{k=v}{y}"],
    ["\\includegraphics", "\\includegraphics{https://x.test/a.png}"],
  ])("cannot create a link or inject an element with %s", (_label, source) => {
    const container = render(`Before $$${source}$$ after`);

    inert(container);
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("#root, .admin, [data-k]")).toBeNull();
    expect(window.__pwned).toBeUndefined();
  });

  it("shows a rejected command as text so the reader still sees what was written", () => {
    const container = render("$$\\href{javascript:window.__pwned=1}{click}$$");

    inert(container);
    expect(container.textContent).toContain("click");
  });

  it("keeps an HTML injection attempt inside a formula as text", () => {
    const container = render('$$x </annotation></semantics></math><img src=x onerror="window.__pwned=1"> $$');

    inert(container);
    expect(container.querySelector("img")).toBeNull();
    expect(window.__pwned).toBeUndefined();
  });

  it("falls back to readable text for malformed formulas and keeps the prose around them", () => {
    const container = render("Start $$\\frac{ $$ middle $$\\left( $$ finish");

    inert(container);
    expect(container.textContent).toContain("Start");
    expect(container.textContent).toContain("middle");
    expect(container.textContent).toContain("finish");
  });

  it("treats an unterminated $$ as plain text", () => {
    const container = render("Open $$ x^2 and never closed");

    inert(container);
    expect(container.textContent).toBe("Open $$ x^2 and never closed");
  });

  it("shows an oversized formula as source instead of typesetting it", () => {
    const source = `$$${"x+".repeat(20_000)}x$$`; // KaTeX took ~5 s on this before the cap
    const started = Date.now();
    const container = render(`Before ${source} after`);

    expect(Date.now() - started).toBeLessThan(2000);
    inert(container);
    expect(container.querySelector(".katex")).toBeNull();
    expect(container.textContent).toBe(`Before ${source} after`);
  });

  it("still typesets a long but reasonable formula", () => {
    const container = render(`$$${"x+".repeat(200)}x$$`);

    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("keeps the passage when KaTeX itself throws (deeply nested input overflows its stack)", () => {
    const spy = vi.spyOn(katex, "renderToString").mockImplementation(() => {
      throw new RangeError("Maximum call stack size exceeded");
    });

    try {
      const container = render("Before $$\\left( x \\right)$$ after");

      expect(container.textContent).toBe("Before $$\\left( x \\right)$$ after");
      expect(window.__pwned).toBeUndefined();
    } finally {
      spy.mockRestore();
    }
  });

  it("does not throw on deeply nested braces", () => {
    const depth = 900;
    const source = `$$${"{".repeat(depth)}x${"}".repeat(depth)}$$`;

    expect(() => render(`Before ${source} after`)).not.toThrow();
  });

  it("keeps a macro-expansion bomb bounded", () => {
    const container = render("$$\\def\\a{\\a\\a}\\a$$ done");

    inert(container);
    expect(container.textContent).toContain("done");
  });
});
