import { useEffect, useRef, useState } from "react";

/** Characters a second when little is waiting, and the most when a lot is. */
const BASE_CPS = 70;
const MAX_CPS = 1400;

/**
 * `target` revealed a character at a time, at a steady pace that quickens when
 * more has arrived than is shown, so a burst of text still reads as typing and
 * never lags far behind. Starts again when `key` changes. `done` is true once
 * everything that has arrived is on screen.
 */
export function useTypewriter(target: string, key: string | undefined) {
  const [shown, setShown] = useState(0);
  const position = useRef(0);
  const latest = useRef(target);
  latest.current = target;

  useEffect(() => { position.current = 0; setShown(0); }, [key]);

  useEffect(() => {
    if (position.current >= target.length) return;
    let last = performance.now();
    const reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    // A timer, not a frame callback: a background tab still finishes the text.
    const timer = setInterval(() => {
      const now = performance.now();
      const goal = latest.current.length;
      const waiting = goal - position.current;
      if (waiting <= 0) { clearInterval(timer); return; }
      const rate = reduced ? Infinity : Math.min(MAX_CPS, BASE_CPS + waiting * 4);
      position.current = Math.min(goal, position.current + Math.max(1, ((now - last) / 1000) * rate));
      last = now;
      setShown(Math.floor(position.current));
    }, 16);
    return () => clearInterval(timer);
  }, [target.length, key]);

  // A reset shrinks the text under the cursor: never show past what exists.
  const count = Math.min(shown, target.length);
  return { text: target.slice(0, count), done: count >= target.length };
}
