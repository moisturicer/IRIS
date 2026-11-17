/**
 * Keeps a drag-selection in a PDF page's text layer from jumping to unrelated
 * text (IR-1209).
 *
 * A text layer is transparent spans laid over the page, with gaps between
 * them (margins, leading, the space between columns). Over a gap the pointer
 * is over no text, so a browser resolves the selection's end to whatever text
 * comes next in the layer's DOM order: another column, a footnote, the end of
 * the page. pdf.js's own viewer avoids it with an `endOfContent` element in
 * each layer and a `selecting` class while a selection is being made (its
 * `TextLayerBuilder`, `web/text_layer_builder.js`). IRIS draws its layers
 * with pdf.js's bare `TextLayer` (`lib/pdf.ts`), which has neither, so this is
 * that behaviour, ported:
 *
 * - every bound layer ends with an `.endOfContent` element; `index.css` keeps
 *   it below the page, and stretches it over the whole layer, behind the
 *   spans, while the layer is `.selecting`, so a gap is over it, not over the
 *   next text;
 * - a press in a layer, or a selection that reaches it, marks it `.selecting`;
 *   releasing the pointer, losing focus or clearing the selection puts every
 *   layer back;
 * - in browsers that still resolve gaps by DOM order (Chromium before 148,
 *   Safari), the element is moved to just after the text where the selection
 *   ends, so a gap resolves to the text the reader is dragging through. Firefox
 *   and Chromium 148+ do not need the move, as in pdf.js.
 *
 * One set of document listeners serves every bound layer, added with the
 * first and removed with the last.
 */

const layers = new Map<HTMLElement, HTMLElement>();
let listeners: AbortController | null = null;
let movesEndElement: boolean | undefined;
let previous: Range | null = null;

function reset(end: HTMLElement, layer: HTMLElement) {
  layer.append(end);
  end.style.width = "";
  end.style.height = "";
  end.style.userSelect = "";
  layer.classList.remove("selecting");
}

function resetAll() {
  layers.forEach(reset);
}

/** Firefox and Chromium 148+ resolve a gap without help (pdf.js's own test). */
function browserMovesEnd(sample: HTMLElement): boolean {
  if (getComputedStyle(sample).getPropertyValue("-moz-user-select") === "none") return false;
  const data = (navigator as Navigator & { userAgentData?: { brands: { brand: string; version: string }[] } }).userAgentData;
  const version = data
    ? data.brands.find(({ brand }) => brand === "Chromium")?.version
    : /\bChrome\/(\d+)\b/.exec(navigator.userAgent)?.[1];
  return !(version && parseInt(version, 10) >= 148);
}

/** The element whose text the selection's moving end is in, outside any find match. */
function anchorOf(range: Range, modifyStart: boolean): Element | null {
  let anchor: Node | null = modifyStart ? range.startContainer : range.endContainer;
  if (anchor?.nodeType === Node.TEXT_NODE) anchor = anchor.parentNode;
  // Find wraps its matches in `<mark>` inside a span (`paintFindHits`); the
  // element belongs beside the span, never inside it.
  if (anchor instanceof Element && anchor.matches("mark")) anchor = anchor.parentNode;
  if (!modifyStart && range.endOffset === 0 && anchor) {
    // The selection ends at the very start of a node: it really ends in the
    // text before it.
    do {
      while (anchor && !anchor.previousSibling) anchor = anchor.parentNode;
      anchor = anchor?.previousSibling ?? null;
    } while (anchor && !anchor.childNodes.length);
  }
  return anchor instanceof Element ? anchor : null;
}

function onSelectionChange() {
  const selection = document.getSelection();
  if (!selection || selection.rangeCount === 0) {
    resetAll();
    previous = null;
    return;
  }
  const active = new Set<HTMLElement>();
  for (let i = 0; i < selection.rangeCount; i++) {
    const range = selection.getRangeAt(i);
    for (const layer of layers.keys()) {
      if (range.intersectsNode(layer)) active.add(layer);
    }
  }
  layers.forEach((end, layer) => {
    if (active.has(layer)) layer.classList.add("selecting");
    else reset(end, layer);
  });

  if (movesEndElement === undefined) movesEndElement = browserMovesEnd(layers.keys().next().value!);
  if (!movesEndElement) return;

  const range = selection.getRangeAt(0);
  const modifyStart = previous !== null && (
    range.compareBoundaryPoints(Range.END_TO_END, previous) === 0
    || range.compareBoundaryPoints(Range.START_TO_END, previous) === 0
  );
  const anchor = anchorOf(range, modifyStart);
  const layer = anchor?.parentElement?.closest<HTMLElement>(".textLayer") ?? null;
  const end = layer ? layers.get(layer) : undefined;
  if (anchor && layer && end && anchor.parentElement) {
    end.style.width = layer.style.width;
    end.style.height = layer.style.height;
    end.style.userSelect = "text";
    anchor.parentElement.insertBefore(end, modifyStart ? anchor : anchor.nextSibling);
  }
  previous = range.cloneRange();
}

function listen() {
  if (listeners) return;
  listeners = new AbortController();
  const { signal } = listeners;
  let pointerDown = false;
  document.addEventListener("pointerdown", () => { pointerDown = true; }, { signal });
  document.addEventListener("pointerup", () => { pointerDown = false; resetAll(); }, { signal });
  window.addEventListener("blur", () => { pointerDown = false; resetAll(); }, { signal });
  document.addEventListener("keyup", () => { if (!pointerDown) resetAll(); }, { signal });
  document.addEventListener("selectionchange", onSelectionChange, { signal });
}

/**
 * Bind one page's text layer, after pdf.js has drawn its spans. Returns the
 * unbind, which removes the layer's `.endOfContent` and, with the last layer,
 * the document listeners.
 */
export function bindTextSelection(layer: HTMLElement): () => void {
  const end = document.createElement("div");
  end.className = "endOfContent";
  layer.append(end);
  const press = new AbortController();
  layer.addEventListener("mousedown", () => layer.classList.add("selecting"), { signal: press.signal });
  layers.set(layer, end);
  listen();

  return () => {
    press.abort();
    layers.delete(layer);
    end.remove();
    layer.classList.remove("selecting");
    if (layers.size === 0) {
      listeners?.abort();
      listeners = null;
      movesEndElement = undefined;
      previous = null;
    }
  };
}
