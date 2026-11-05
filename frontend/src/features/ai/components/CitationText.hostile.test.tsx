/**
 * Hostile input to AI answer text (IR-917).
 *
 * An answer is model output built from retrieved manuscripts, so it is
 * untrusted: a paper can carry markup, a link or a formula written to do
 * something when it is shown. `CitationText` is the one place that text becomes
 * DOM (react-markdown, no `rehype-raw`, KaTeX with `trust` off). Each test
 * feeds one attack and asserts the *result*: nothing executed, no element or
 * attribute the app did not choose, and readable text left behind.
 */
import { afterEach, describe, expect, it } from "vitest";

import { anchors, expectInert } from "@/test/hostile";
import { renderScreen, screen } from "@/test/render";
import type { Citation } from "@/types/ai";

import { CitationText } from "./CitationText";

declare global {
  interface Window {
    __pwned?: unknown;
  }
}

afterEach(() => {
  delete window.__pwned;
});

const citation: Citation = {
  marker: 1,
  chunk_id: 11,
  record_id: 7,
  record_title: "Flood Prediction in the Mananga Catchment",
  page: 4,
  text: "we trained a convolutional neural network",
  context_path: ["Flood Prediction in the Mananga Catchment"],
  regions: [],
};

function render(text: string, citations: Citation[] = []) {
  const view = renderScreen(<CitationText text={text} citations={citations} />);
  return view.container;
}

describe("raw HTML in an answer", () => {
  it("never creates a script element or runs one", () => {
    const container = render("Before <script>window.__pwned = 1</script> after");

    expectInert(container);
    expect(window.__pwned).toBeUndefined();
  });

  it("never creates an image, so an onerror handler has nothing to attach to", () => {
    const container = render('<img src=x onerror="window.__pwned = 1"> and ![x](https://x.test/a.png)');

    expectInert(container);
    expect(container.querySelector("img")).toBeNull();
    expect(window.__pwned).toBeUndefined();
  });

  it.each([
    ["an iframe", '<iframe src="https://evil.test"></iframe>'],
    ["an svg onload", '<svg onload="window.__pwned = 1"><circle/></svg>'],
    ["an object", '<object data="data:text/html,<script>1</script>"></object>'],
    ["a form", '<form action="https://evil.test"><input name="pw"><button>Go</button></form>'],
    ["an inline handler on a div", '<div onclick="window.__pwned = 1" style="position:fixed;inset:0">cover</div>'],
    ["a style element", "<style>body{display:none}</style>"],
    ["a meta refresh", '<meta http-equiv="refresh" content="0;url=https://evil.test">'],
    ["a details toggle", '<details open ontoggle="window.__pwned = 1">x</details>'],
  ])("renders %s as inert text, not an element", (_label, html) => {
    const container = render(`Intro\n\n${html}\n\nOutro`);

    expectInert(container);
    expect(container.querySelector("[style]")).toBeNull();
    expect(window.__pwned).toBeUndefined();
    expect(screen.getByText(/Intro/)).toBeTruthy();
    expect(screen.getByText(/Outro/)).toBeTruthy();
  });

  it("does not decode an HTML-entity-encoded script into a live one", () => {
    const container = render("&lt;script&gt;window.__pwned = 1&lt;/script&gt; &#60;img src=x onerror=alert(1)&#62;");

    expectInert(container);
    expect(window.__pwned).toBeUndefined();
  });
});

describe("links in an answer", () => {
  it.each([
    ["javascript:", "[click me](javascript:window.__pwned=1)"],
    ["JavaScript: in mixed case", "[click me](JaVaScRiPt:window.__pwned=1)"],
    ["javascript: with an encoded colon", "[click me](javascript&#58;window.__pwned=1)"],
    ["javascript: with a tab inside the scheme", "[click me](java\tscript:window.__pwned=1)"],
    ["javascript: with a leading space", "[click me]( javascript:window.__pwned=1)"],
    ["data: text/html", "[click me](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)"],
    ["data: image/svg+xml", "[click me](data:image/svg+xml,<svg onload=alert(1)>)"],
    ["vbscript:", "[click me](vbscript:msgbox(1))"],
    ["file:", "[click me](file:///etc/passwd)"],
    ["blob:", "[click me](blob:https://x.test/abc)"],
  ])("drops the href of a %s link and keeps its text", (_label, markdown) => {
    const container = render(markdown);

    expectInert(container);
    for (const link of anchors(container)) {
      expect(link.href ?? "").not.toMatch(/^\s*(javascript|data|vbscript|file|blob)/i);
    }
    expect(container.textContent).toContain("click me");
    expect(window.__pwned).toBeUndefined();
  });

  it("drops a javascript: reference-style link and an autolink the same way", () => {
    const container = render("[a][r] and <javascript:window.__pwned=1>\n\n[r]: javascript:window.__pwned=1");

    expectInert(container);
    expect(window.__pwned).toBeUndefined();
  });

  it("opens an ordinary https link in a new tab without leaking the opener", () => {
    const container = render("See [the standard](https://example.org/spec).");

    const [link] = Array.from(container.querySelectorAll("a"));
    expect(link.getAttribute("href")).toBe("https://example.org/spec");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noreferrer");
  });

  it("does not let answer text forge a citation chip for a marker with no citation", () => {
    const container = render("[fake](iris-citation:99) and [forged](iris-citation:../../admin)", [citation]);

    expectInert(container);
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("does not let a literal iris-citation link in the text point a chip at the wrong paper", () => {
    render("[x](iris-citation:1)", [citation]);

    const chip = screen.getByRole("link", { name: /Open Flood Prediction/i });
    expect(chip.getAttribute("href")).toBe("/records/7?page=4");
  });

  it("keeps a hostile record title inside the chip's attributes, never as markup", () => {
    const hostile: Citation = { ...citation, record_title: '"><img src=x onerror="window.__pwned=1">' };
    const container = render("A claim [1].", [hostile]);

    expectInert(container);
    expect(container.querySelector("img")).toBeNull();
    expect(window.__pwned).toBeUndefined();
  });
});

describe("HTML inside a citation marker or a code span", () => {
  it("keeps markup in a streamed citation-shaped span as text", () => {
    const view = renderScreen(
      <CitationText text="Claim [1 <img src=x onerror=alert(1)>] more" citations={[]} streaming />,
    );

    expectInert(view.container);
  });

  it("shows markup in a code span and a fenced block as source text", () => {
    const container = render("`<script>x</script>`\n\n```html\n<img src=x onerror=alert(1)>\n```");

    expectInert(container);
    expect(container.textContent).toContain("<script>x</script>");
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});

describe("hostile mathematics in an answer", () => {
  const math = (text: string) => render(text);
  const inertMath = (container: HTMLElement) => expectInert(container, { allowTags: ["svg"] });

  it.each([
    ["\\href to a javascript: URL", "$\\href{javascript:window.__pwned=1}{click}$"],
    ["\\url to a javascript: URL", "$\\url{javascript:window.__pwned=1}$"],
    ["\\href to a data: URL", "$$\\href{data:text/html,<script>1</script>}{click}$$"],
    ["\\htmlId", "$\\htmlId{x}{y}$"],
    ["\\htmlClass", "$\\htmlClass{admin}{y}$"],
    ["\\htmlStyle", "$\\htmlStyle{position:fixed}{y}$"],
    ["\\htmlData", "$\\htmlData{k=v}{y}$"],
    ["\\includegraphics", "$\\includegraphics{https://x.test/a.png}$"],
  ])("cannot make a link, element or handler with %s", (_label, source) => {
    const container = math(`Before ${source} after`);

    inertMath(container);
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("[id='x'], .admin, [data-k]")).toBeNull();
    expect(window.__pwned).toBeUndefined();
  });

  it("shows an HTML injection attempt inside a formula as text", () => {
    const container = math('$$x </annotation></semantics></math><img src=x onerror="window.__pwned=1"> $$');

    inertMath(container);
    expect(container.querySelector("img")).toBeNull();
    expect(window.__pwned).toBeUndefined();
  });

  it("falls back to readable source for a malformed formula rather than throwing", () => {
    const container = math("Broken $$\\frac{ $$ then text");

    inertMath(container);
    expect(container.textContent).toContain("then text");
  });

  it("survives an unbalanced and a deeply nested formula", () => {
    const nested = `$${"{".repeat(2000)}x${"}".repeat(2000)}$`;
    const container = math(`${nested} $\\left( x $ tail`);

    inertMath(container);
    expect(container.textContent).toContain("tail");
  });

  it.each([
    ["displayed", (body: string) => `\n\n$$\n${body}\n$$\n\n`],
    ["inline", (body: string) => `$${body}$`],
  ])("shows an oversized %s formula as source instead of typesetting it", (_label, wrap) => {
    // No `+` between terms: remark-gfm's email autolink is quadratic on that
    // shape, which would time the test on the parser, not on the formula.
    const body = "x ".repeat(20_000) + "x";
    const started = Date.now();
    const container = math(`Before ${wrap(body)} after`);

    expect(Date.now() - started).toBeLessThan(2000);
    inertMath(container);
    expect(container.querySelector(".katex")).toBeNull();
    expect(container.textContent).toContain("x x x x ");
    expect(container.textContent).toContain("Before");
  });

  it("still typesets a long but reasonable formula", () => {
    const container = math(`$$${"x+".repeat(200)}x$$`);

    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("keeps a TeX macro-expansion bomb bounded", () => {
    const container = math("$\\def\\a{\\a\\a}\\a$ done");

    inertMath(container);
    expect(container.textContent).toContain("done");
  });
});
