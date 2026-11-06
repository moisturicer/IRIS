/**
 * A passage of the paper, as an anchor records it (ADR-032 §7, 2026-11-04;
 * IR-875): the page, the quote, the text either side so a later Version can
 * find it again (ADR-058), and its regions in ADR-031's page-fraction format.
 *
 * The geometry and the context are pure, so they are tested without a layout
 * engine; `passageFromRange` only reads the DOM and hands them its numbers.
 */
import type { PageRegion } from "@/types/records";

/** Enough of each side to find the passage again; the server allows 500. */
export const CONTEXT_CHARS = 64;

/** What the backend accepts for a quote (`comments.MAX_QUOTE_LENGTH`). */
export const MAX_QUOTE = 2_000;

export interface Box {
  left: number; top: number; right: number; bottom: number; width: number; height: number;
}

export interface Passage {
  page:    number;
  quote:   string;
  prefix:  string;
  suffix:  string;
  regions: PageRegion[];
}

const collapse = (text: string) => text.replace(/\s+/g, " ");
const fraction = (n: number) => Math.round(Math.min(1, Math.max(0, n)) * 10_000) / 10_000;

/**
 * Each rect as fractions of the page it falls on, clipped to it. Empty rects
 * (a browser's zero-width line ends) and rects on no page are dropped.
 */
export function regionsFromRects(rects: readonly Box[], pages: readonly { page: number; box: Box }[]): PageRegion[] {
  const regions: PageRegion[] = [];
  for (const r of rects) {
    if (r.width <= 0 || r.height <= 0) continue;
    // The page it overlaps most: a line's box can stick out past the page's edge.
    let on: (typeof pages)[number] | undefined;
    let best = 0;
    for (const p of pages) {
      const overlap = Math.min(r.bottom, p.box.bottom) - Math.max(r.top, p.box.top);
      if (p.box.width > 0 && p.box.height > 0 && overlap > best) { best = overlap; on = p; }
    }
    if (!on) continue;
    const { box } = on;
    const region = {
      page: on.page,
      left: fraction((r.left - box.left) / box.width),
      top: fraction((r.top - box.top) / box.height),
      right: fraction((r.right - box.left) / box.width),
      bottom: fraction((r.bottom - box.top) / box.height),
    };
    if (region.left < region.right && region.top < region.bottom) regions.push(region);
  }
  return regions;
}

/** Up to `n` characters of the page's text either side of the quote's first occurrence. */
export function contextAround(pageText: string, quote: string, n = CONTEXT_CHARS): { prefix: string; suffix: string } {
  const text = collapse(pageText);
  const q = collapse(quote).trim();
  const at = q ? text.indexOf(q) : -1;
  if (at < 0) return { prefix: "", suffix: "" };
  return { prefix: text.slice(Math.max(0, at - n), at), suffix: text.slice(at + q.length, at + q.length + n) };
}

/** The quote as it is stored: whitespace collapsed, trimmed and bounded. */
export const normalizeQuote = (text: string) => collapse(text).trim().slice(0, MAX_QUOTE);

/**
 * The passage a DOM range selects in the reader, or null when it is not on a
 * page's text. `pageOf` finds the page box an element sits in.
 */
export function passageFromRange(range: Range, root: HTMLElement): Passage | null {
  const quote = normalizeQuote(range.toString());
  if (quote.length < 2) return null;
  const startNode = range.startContainer instanceof Element ? range.startContainer : range.startContainer.parentElement;
  const pageEl = startNode?.closest<HTMLElement>("[data-page-number]");
  if (!pageEl || !root.contains(pageEl)) return null;
  const page = Number(pageEl.dataset.pageNumber);
  const pages = Array.from(root.querySelectorAll<HTMLElement>("[data-page-number]")).map((el) => ({
    page: Number(el.dataset.pageNumber), box: el.getBoundingClientRect(),
  }));
  const layer = pageEl.querySelector(".textLayer");
  const { prefix, suffix } = contextAround(layer?.textContent ?? "", quote);
  return { page, quote, prefix, suffix, regions: regionsFromRects(rectsOf(range), pages) };
}

/** A range's line boxes; none where the browser draws no layout (jsdom). */
function rectsOf(range: Range): Box[] {
  return typeof range.getClientRects === "function" ? Array.from(range.getClientRects()) : [];
}
