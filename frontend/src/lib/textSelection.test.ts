import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { bindTextSelection } from "./textSelection";

/**
 * IR-1209: selecting text in the paper reader jumped to unrelated text. The
 * gaps between a page's text spans belonged to nothing, so the browser
 * resolved a drag over them to whatever text came next in the page. pdf.js's
 * own viewer fixes this with an `endOfContent` element and a `selecting`
 * class; `bindTextSelection` is that fix for IRIS's text layers.
 *
 * jsdom has real ranges and selections but no layout, so these tests pin the
 * DOM the fix depends on; the drag itself is checked in a real browser by
 * e2e/smoke/text-selection.spec.ts.
 *
 * These tests find the end element and the spans by class and position, not
 * by role and name as the frontend's tests otherwise do (CLAUDE.md): the
 * element has no role or name, and its place in the DOM is what is tested.
 */

const unbinds: Array<() => void> = [];

function page(...lines: string[]): HTMLDivElement {
  const layer = document.createElement("div");
  layer.className = "textLayer";
  for (const line of lines) {
    const span = document.createElement("span");
    span.textContent = line;
    layer.append(span);
  }
  document.body.append(layer);
  unbinds.push(bindTextSelection(layer));
  return layer;
}

const end = (layer: HTMLElement) => layer.querySelector(".endOfContent");
const spans = (layer: HTMLElement) => [...layer.querySelectorAll(":scope > span")];

function select(startNode: Node, startOffset: number, endNode: Node, endOffset: number) {
  const range = document.createRange();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
  document.dispatchEvent(new Event("selectionchange"));
}

beforeEach(() => {
  window.getSelection()?.removeAllRanges();
});

afterEach(() => {
  while (unbinds.length) unbinds.pop()!();
  document.body.replaceChildren();
  vi.unstubAllGlobals();
});

describe("bindTextSelection (IR-1209)", () => {
  it("gives the layer one end-of-content element, after its text", () => {
    const layer = page("First line", "Second line");

    expect(layer.querySelectorAll(".endOfContent")).toHaveLength(1);
    expect(layer.lastElementChild).toBe(end(layer));
  });

  it("marks the layer as selecting from the press until the pointer is released", () => {
    const layer = page("First line");

    layer.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    expect(layer).toHaveClass("selecting");

    document.dispatchEvent(new Event("pointerup"));
    expect(layer).not.toHaveClass("selecting");
  });

  it("marks only the pages the selection touches", () => {
    const first = page("Page one text");
    const second = page("Page two text");

    select(spans(first)[0].firstChild!, 0, spans(first)[0].firstChild!, 4);

    expect(first).toHaveClass("selecting");
    expect(second).not.toHaveClass("selecting");
  });

  it("moves the end-of-content element to just after where the selection ends", () => {
    const layer = page("One", "Two", "Three");
    const [one, two, three] = spans(layer);

    select(one.firstChild!, 0, two.firstChild!, 2);

    expect(two.nextElementSibling).toBe(end(layer));
    expect(end(layer)?.nextElementSibling).toBe(three);
  });

  it("steps out of a find match, so the element never lands inside a word", () => {
    const layer = page("One", "");
    const [one, withMatch] = spans(layer);
    const mark = document.createElement("mark");
    mark.className = "find-hit";
    mark.textContent = "rain";
    withMatch.append(mark, document.createTextNode("water"));

    select(one.firstChild!, 0, mark.firstChild!, 2);

    expect(withMatch.querySelector(".endOfContent")).toBeNull();
    expect(withMatch.nextElementSibling).toBe(end(layer));
  });

  it("puts everything back when the selection is cleared", () => {
    const layer = page("One", "Two");
    const [one, two] = spans(layer);
    select(one.firstChild!, 0, two.firstChild!, 1);

    window.getSelection()!.removeAllRanges();
    document.dispatchEvent(new Event("selectionchange"));

    expect(layer).not.toHaveClass("selecting");
    expect(layer.lastElementChild).toBe(end(layer));
  });

  it("puts everything back when the window loses focus mid-drag", () => {
    const layer = page("One");
    layer.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));

    window.dispatchEvent(new Event("blur"));

    expect(layer).not.toHaveClass("selecting");
  });

  it("leaves the element in place in a browser that resolves the gaps itself (Chromium 148+)", () => {
    vi.stubGlobal("navigator", { ...navigator, userAgentData: undefined, userAgent: "Mozilla/5.0 Chrome/150.0 Safari/537.36" });
    const layer = page("One", "Two", "Three");
    const [one, two] = spans(layer);

    select(one.firstChild!, 0, two.firstChild!, 2);

    expect(layer).toHaveClass("selecting");
    expect(layer.lastElementChild).toBe(end(layer));
  });

  it("leaves the element in place in Firefox, which resolves the gaps itself", () => {
    // Firefox reports the end element's own `user-select: none` (index.css)
    // as `-moz-user-select`; the layer's text is selectable, so the check is
    // made on the end element, as pdf.js makes it.
    const real = window.getComputedStyle.bind(window);
    vi.spyOn(window, "getComputedStyle").mockImplementation((element, pseudo) => {
      const style = real(element, pseudo);
      if (!(element as Element).classList.contains("endOfContent")) return style;
      return { ...style, getPropertyValue: (name: string) => (name === "-moz-user-select" ? "none" : style.getPropertyValue(name)) } as CSSStyleDeclaration;
    });
    const layer = page("One", "Two", "Three");
    const [one, two] = spans(layer);

    select(one.firstChild!, 0, two.firstChild!, 2);

    expect(layer).toHaveClass("selecting");
    expect(layer.lastElementChild).toBe(end(layer));
    vi.restoreAllMocks();
  });

  it("unbinding removes the element and stops reacting", () => {
    const layer = page("One");
    unbinds.pop()!();

    expect(end(layer)).toBeNull();
    layer.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    expect(layer).not.toHaveClass("selecting");
  });
});
