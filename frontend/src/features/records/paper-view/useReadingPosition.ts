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
  /**
   * Changes when pages take their real size in place of an estimate (IR-565):
   * the pages above the reader may have moved, so their place is put back.
   */
  geometryKey: string | number;
}

/** Where the reader is: the page under the toolbar, and the last page in view. */
export interface ReadingPosition {
  currentPage: number;
  lastVisiblePage: number;
}

const START: ReadingPosition = { currentPage: 1, lastVisiblePage: 1 };

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
 * the same page back under the toolbar before the browser paints. So it does
 * when a page loads at a size other than the one estimated for it (IR-565).
 *
 * The last page in view is what, with the current one, decides which pages
 * the reader paints (`liveWindow`).
 */
export function useReadingPosition({
  ready,
  pageCount,
  scale,
  pageRefs,
  toolbarRef,
  scrollAreaRef,
  contained,
  geometryKey,
}: ReadingPositionOptions): ReadingPosition {
  const [position, setPosition] = useState<ReadingPosition>(START);
  const anchorRef = useRef<ReadingAnchor | null>(null);

  const viewTop = useCallback(
    () => toolbarRef.current?.getBoundingClientRect().bottom ?? 0,
    [toolbarRef],
  );

  /** The bottom of what can be read: the pane's when it scrolls, else the window's. */
  const viewBottom = useCallback(() => {
    const area = scrollAreaRef.current;
    if (area && /auto|scroll/.test(getComputedStyle(area).overflowY)) {
      return area.getBoundingClientRect().bottom;
    }
    return window.innerHeight;
  }, [scrollAreaRef]);

  useEffect(() => {
    if (ready) return;
    anchorRef.current = null;
    setPosition(START);
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
      const bottom = viewBottom();
      let last = anchor.page;
      while (last < boxes.length && boxes[last].top < bottom) last += 1;
      setPosition((previous) =>
        previous.currentPage === anchor.page && previous.lastVisiblePage === last
          ? previous
          : { currentPage: anchor.page, lastVisiblePage: last },
      );
    };
    const onScroll = () => {
      if (!cancelFrame) cancelFrame = nextFrame(measure);
    };

    const area = scrollAreaRef.current;
    area?.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    // Once on opening and on every zoom: a paper opened at 40% shows more
    // pages than one at 140%, before anything has scrolled.
    onScroll();
    return () => {
      cancelFrame?.();
      area?.removeEventListener("scroll", onScroll);
      window.removeEventListener("scroll", onScroll);
    };
  }, [ready, pageCount, scale, pageRefs, scrollAreaRef, viewTop, viewBottom]);

  const layoutKey = `${scale}|${contained}|${geometryKey}`;
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

  return position;
}
