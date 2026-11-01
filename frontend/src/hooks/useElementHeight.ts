import { useEffect, useState } from "react";

/**
 * An element's border-box height, kept current by a `ResizeObserver`
 * (IR-477) -- padding and border included, because what it is for is how
 * much of the screen the element covers. 0 until it is measured, while
 * there is no element, and wherever it cannot be measured (jsdom).
 *
 * Returns a callback ref, as `useElementWidth` does, so an element that
 * unmounts and comes back is observed afresh.
 */
export function useElementHeight<T extends HTMLElement>(): [(element: T | null) => void, number] {
  const [element, setElement] = useState<T | null>(null);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    if (!element || typeof ResizeObserver === "undefined") {
      setHeight(0);
      return;
    }
    const observer = new ResizeObserver(([entry]) => {
      const box = entry.borderBoxSize?.[0];
      setHeight(Math.ceil(box ? box.blockSize : entry.target.getBoundingClientRect().height));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);

  return [setElement, height];
}
