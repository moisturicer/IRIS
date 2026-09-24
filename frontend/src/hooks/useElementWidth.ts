import { useEffect, useState } from "react";

/**
 * An element's content-box width, kept current by a `ResizeObserver`
 * (IR-352). 0 until it is measured, and wherever it cannot be (jsdom).
 *
 * Returns a callback ref rather than taking a `RefObject`, so an element
 * that unmounts and comes back -- a reader recovering from an error, say --
 * is observed afresh instead of the observer watching the detached one.
 *
 * The first measurement applies at once. Later ones wait until the width
 * has held for `settleMs`, since a window drag reports every frame and
 * whatever depends on the width may be expensive to redo.
 */
export function useElementWidth<T extends HTMLElement>(
  settleMs = 0,
): [(element: T | null) => void, number] {
  const [element, setElement] = useState<T | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    if (!element || typeof ResizeObserver === "undefined") return;
    let timer: number | undefined;
    let measured = false;

    const observer = new ResizeObserver(([entry]) => {
      const next = Math.round(entry.contentRect.width);
      window.clearTimeout(timer);
      if (!measured || settleMs <= 0) {
        measured = true;
        setWidth(next);
        return;
      }
      timer = window.setTimeout(() => setWidth(next), settleMs);
    });
    observer.observe(element);

    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
    };
  }, [element, settleMs]);

  return [setElement, width];
}
