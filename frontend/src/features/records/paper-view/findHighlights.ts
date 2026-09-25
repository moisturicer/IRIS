/**
 * Paints find's matches onto a page's text layer (IR-353).
 *
 * The text layer is pdf.js's, not React's: its spans are created by
 * `TextLayer` outside the component tree, so they are marked up directly.
 * Each span's own text is wrapped where it matches, in a `<mark>` -- inside
 * the span, so the highlight takes the span's position, font size and
 * horizontal scale, and stays on the words at any zoom.
 */
import type { FindHit } from "./findInPaper";

/** Each painted span's text as pdf.js drew it, to restore when the find changes. */
const originals = new WeakMap<HTMLElement, string>();

export const FIND_HIT_CLASS = "find-hit";
export const FIND_HIT_CURRENT_CLASS = "find-hit-current";

/**
 * Replaces whatever was painted on `spans` with `hits`. An empty `hits`
 * clears the page, leaving each span with its plain text again.
 */
export function paintFindHits(spans: HTMLElement[], hits: FindHit[]): void {
  for (const span of spans) {
    const original = originals.get(span);
    if (original !== undefined) {
      span.textContent = original;
      originals.delete(span);
    }
  }

  const byRun = new Map<number, { start: number; end: number; current: boolean }[]>();
  for (const hit of hits) {
    for (const piece of hit.pieces) {
      const pieces = byRun.get(piece.run) ?? [];
      pieces.push({ start: piece.start, end: piece.end, current: hit.current });
      byRun.set(piece.run, pieces);
    }
  }

  byRun.forEach((pieces, run) => {
    const span = spans[run];
    if (!span) return;
    const text = span.textContent ?? "";
    originals.set(span, text);
    pieces.sort((a, b) => a.start - b.start);

    const fragment = document.createDocumentFragment();
    let at = 0;
    for (const { start, end, current } of pieces) {
      if (start > at) fragment.append(text.slice(at, start));
      const mark = document.createElement("mark");
      mark.className = current ? `${FIND_HIT_CLASS} ${FIND_HIT_CURRENT_CLASS}` : FIND_HIT_CLASS;
      mark.textContent = text.slice(start, end);
      fragment.append(mark);
      at = end;
    }
    if (at < text.length) fragment.append(text.slice(at));
    span.replaceChildren(fragment);
  });
}
