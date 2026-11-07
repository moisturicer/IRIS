/**
 * Shared assertions for hostile-content render tests (IR-917).
 *
 * "Inert" means the rendered DOM could not run script or navigate somewhere the
 * app did not choose: no executable or embedding element, no inline event
 * handler, no link or form target on a script-capable scheme, no inline style
 * attribute carrying a `url(...)` / `expression(...)`. The check walks the
 * whole subtree, so it also covers what KaTeX writes through
 * `dangerouslySetInnerHTML`.
 */
import { expect } from "vitest";

/** Elements that run code, load a document, or restyle the page. */
const FORBIDDEN_TAGS = ["script", "iframe", "object", "embed", "form", "base", "meta", "link", "style", "img", "svg", "video", "audio"];

/** URL-bearing attributes the browser follows or loads. */
const URL_ATTRIBUTES = ["href", "src", "xlink:href", "action", "formaction", "data", "srcset", "poster"];

/** Anything but these schemes (or a relative URL) is a way out of the app. */
const SAFE_SCHEME = /^(https?:|mailto:|tel:|#|\/(?!\/)|\?|\.{0,2}\/?[\w-])/i;


export interface InertOptions {
  /** Tags the surface legitimately emits that would otherwise be forbidden. */
  allowTags?: string[];
}

/** Drop controls, spaces and NBSP (code points up to U+0020, and U+00A0): browsers ignore them inside a URL scheme. */
function normalizedUrl(value: string): string {
  return Array.from(value)
    .filter((char) => (char.codePointAt(0) ?? 0) > 0x20 && char !== " ")
    .join("")
    .toLowerCase();
}

export function expectInert(root: ParentNode, { allowTags = [] }: InertOptions = {}): void {
  const forbidden = FORBIDDEN_TAGS.filter((tag) => !allowTags.includes(tag));
  for (const tag of forbidden) {
    expect(root.querySelectorAll(tag), `<${tag}> element in rendered output`).toHaveLength(0);
  }

  for (const element of Array.from(root.querySelectorAll("*"))) {
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      expect(name.startsWith("on"), `inline handler ${attribute.name} on <${element.localName}>`).toBe(false);

      if (URL_ATTRIBUTES.includes(name)) {
        const value = normalizedUrl(attribute.value);
        expect(
          /^(javascript|data|vbscript|file|blob):/.test(value),
          `${attribute.name}="${attribute.value}" on <${element.localName}>`,
        ).toBe(false);
        expect(SAFE_SCHEME.test(value), `${attribute.name}="${attribute.value}" on <${element.localName}>`).toBe(true);
      }

      if (name === "style") {
        expect(/url\(|expression\(|javascript:|@import/i.test(attribute.value), `style="${attribute.value}"`).toBe(false);
      }
    }
  }
}

/** Every anchor in the subtree, as `{ href, text }`. */
export function anchors(root: ParentNode): { href: string | null; text: string }[] {
  return Array.from(root.querySelectorAll("a")).map((a) => ({ href: a.getAttribute("href"), text: a.textContent ?? "" }));
}
