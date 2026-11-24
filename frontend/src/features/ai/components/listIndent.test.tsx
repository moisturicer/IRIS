import { expect, test } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CitationText } from "./CitationText";
import { nestLists } from "./listIndent";

function html(text: string) {
  const { container } = render(<MemoryRouter><CitationText text={text} citations={[]} /></MemoryRouter>);
  return container;
}

test("a sub-list indented two spaces under a numbered item stays inside it, and the numbering does not restart", () => {
  const view = html("1. **Models the front.** A surrogate.\n  - Gaussian process\n  - active learning\n2. **Scores candidates.**");
  const ol = view.querySelector("ol")!;
  expect(view.querySelectorAll("ol")).toHaveLength(1);
  expect(ol.querySelectorAll(":scope > li")).toHaveLength(2);
  expect(ol.querySelector(":scope > li:first-child > ul")?.textContent).toContain("Gaussian process");
});

test("a continuation line indented two spaces stays in its numbered item", () => {
  const view = html("1. First item\n2. Second item\n  Expected hypervolume is maximised.\n3. Third item");
  expect(view.querySelectorAll("ol")).toHaveLength(1);
  expect(view.querySelector("ol > li:nth-child(2)")?.textContent).toContain("Expected hypervolume");
});

test("one-space and three-space nesting under bullets and wide numbers nests one level each", () => {
  const view = html("10. Tenth\n   - nested under ten\n- Bullet\n - one-space child\n    - grandchild");
  expect(view.querySelector("ol > li > ul")?.textContent).toContain("nested under ten");
  expect(view.querySelector("ul > li > ul > li > ul")?.textContent).toContain("grandchild");
});

test("text already indented correctly, prose and fenced code are left exactly as written", () => {
  const right = "1. One\n   - child\n2. Two";
  expect(nestLists(right)).toBe(right);
  const prose = "A paragraph.\n\nAnother one.";
  expect(nestLists(prose)).toBe(prose);
  const code = "```\n1. not a list\n  - nor this\n```";
  expect(nestLists(code)).toBe(code);
});

test("text at the margin after a blank line ends the list", () => {
  expect(nestLists("1. One\n\nAfter the list.\n  indented code-ish")).toBe("1. One\n\nAfter the list.\n  indented code-ish");
});
