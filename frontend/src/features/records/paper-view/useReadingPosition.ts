import { useCallback, useEffect, useLayoutEffect, useRef, useState, type MutableRefObject, type RefObject } from "react";
import { anchorDelta, readingAnchor, type ReadingAnchor } from "./readerGeometry";

interface ReadingPositionOptions {
  /** Whether the pages are rendered and can be measured. */
  ready: boolean;
  pageCount: number;
  /** The current zoom; a change moves every page. */
  scale: number;
  pageRefs: MutableRefObject<Map<number, HTMLDivElement>>;
  /** The reader's toolbar: its bottom edge is the top of what can be read. */
  toolbarRef: RefObject<HTMLElement>;
  /** The pane's scroll area, which scrolls the pages when contained. */
  scrollAreaRef: MutableRefObject<HTMLElement | null>;
  /** The reader is a contained pane (IR-569); a change swaps the scroller. */
  contained: boolean;
}

/** Throttles to the next frame where the browser offers one. */
function nextFrame(callback: () => void): () => void {
  if (typeof window.requestAnimationFrame === "function") {
    const id = window.requestAnimationFrame(callback);
    return () => window.cancelAnimationFrame(id);
  }
  const id = window.setTimeout(callback, 16);
  return () => window.clearTimeout(id);
}

/**
 * Where the reader is in the paper, and keeping them there (IR-352).
 *
 * Tracks the page under the toolbar as either scroller moves -- the pane at
 * when contained, the window otherwise -- and returns its number for
 * "Page n / N". When the zoom changes, or the workspace crosses into or out of
 * the contained layout (which swaps the scroller), it puts the same point of
 * the same page back under the toolbar before the browser paints.
 */
export function useReadingPosition({
  ready,
  pageCount,
  scale,
  pageRefs,
  toolbarRef,
  scrollAreaRef,
  contained,
}: ReadingPositionOptions): number {
  const [currentPage, setCurrentPage] = useState(1);
  const anchorRef = useRef<ReadingAnchor | null>(null);

  const viewTop = useCallback(
    () => toolbarRef.current?.getBoundingClientRect().bottom ?? 0,
    [toolbarRef],
  );

  useEffect(() => {
    if (ready) return;
    anchorRef.current = null;
    setCurrentPage(1);
  }, [ready]);

  useEffect(() => {
    if (!ready) return;
    let cancelFrame: (() => void) | null = null;

    const measure = () => {
      cancelFrame = null;
      const boxes = Array.from({ length: pageCount }, (_, i) => {
        const rect = pageRefs.current.get(i + 1)?.getBoundingClientRect();
        return { top: rect?.top ?? 0, height: rect?.height ?? 0 };
      });
      if (boxes.every((box) => box.height === 0)) return; // not laid out
      const anchor = readingAnchor(boxes, viewTop());
      if (!anchor) return;
      anchorRef.current = anchor;
      setCurrentPage(anchor.page);
    };
    const onScroll = () => {
      if (!cancelFrame) cancelFrame = nextFrame(measure);
    };

    const area = scrollAreaRef.current;
    area?.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelFrame?.();
      area?.removeEventListener("scroll", onScroll);
      window.removeEventListener("scroll", onScroll);
    };
  }, [ready, pageCount, pageRefs, scrollAreaRef, viewTop]);

  const layoutKey = `${scale}|${contained}`;
  const lastLayoutKey = useRef(layoutKey);
  useLayoutEffect(() => {
    if (lastLayoutKey.current === layoutKey) return;
    lastLayoutKey.current = layoutKey;
    const anchor = anchorRef.current;
    const page = anchor && pageRefs.current.get(anchor.page);
    if (!anchor || !page) return;

    const rect = page.getBoundingClientRect();
    const delta = anchorDelta({ top: rect.top, height: rect.height }, anchor.fraction, viewTop());
    if (Math.abs(delta) < 1) return;

    const area = scrollAreaRef.current;
    const areaScrolls = area && /auto|scroll/.test(getComputedStyle(area).overflowY);
    if (area && areaScrolls) area.scrollTop += delta;
    else window.scrollBy(0, delta);
    // Refs and `viewTop` are stable: only a change of layout runs this.
  }, [layoutKey, pageRefs, scrollAreaRef, viewTop]);

  return currentPage;
}
