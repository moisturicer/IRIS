import { useEffect, useRef, useState } from "react";

/** Slowest pace, and the fastest a large backlog can push it to (characters a second). */
const MIN_CPS = 120;
const MAX_CPS = 2400;
/** Whatever is waiting is aimed to be on screen within this long. */
const CATCH_UP_S = 2;
/** How quickly the pace follows its goal; lower is gentler. */
const EASE_PER_S = 8;
/** Short holds after a sentence or a paragraph, so the text breathes. */
const SENTENCE_PAUSE_MS = 90;
const PARAGRAPH_PAUSE_MS = 180;

/** The end of the last whole word at or before `at`, so a word never shows half-typed. */
function wordEnd(text: string, at: number): number {
  if (at >= text.length) return text.length;
  const space = text.lastIndexOf(" ", at);
  const line = text.lastIndexOf("\n", at);
  return Math.max(space, line, 0);
}

/**
 * `target` revealed word by word at a pace that eases toward clearing the backlog
 * in about CATCH_UP_S, with small pauses at sentence and paragraph ends. Starts
 * again when `key` changes. `done` is true once everything that arrived is shown.
 */
export function useTypewriter(target: string, key: string | undefined) {
  const [shown, setShown] = useState(0);
  const position = useRef(0);
  const speed = useRef(MIN_CPS);
  const goal = useRef(MIN_CPS);
  const latest = useRef(target);
  latest.current = target;

  useEffect(() => { position.current = 0; speed.current = MIN_CPS; setShown(0); }, [key]);

  useEffect(() => {
    if (position.current >= target.length) return;
    // Set when text arrives, not every frame, so the reveal runs at an even pace and lands on time.
    goal.current = Math.min(MAX_CPS, Math.max(MIN_CPS, (target.length - position.current) / CATCH_UP_S));
    const reduced = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) { position.current = target.length; setShown(target.length); return; }
    let last = performance.now();
    let holdUntil = 0;
    let frame = 0;
    let timer = 0;
    let stopped = false;
    const tick = () => {
      cancelAnimationFrame(frame);
      clearTimeout(timer);
      if (stopped) return;
      const now = performance.now();
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const text = latest.current;
      const waiting = text.length - position.current;
      if (waiting <= 0) return;
      if (now >= holdUntil) {
        speed.current += (goal.current - speed.current) * Math.min(1, dt * EASE_PER_S);
        const before = position.current;
        position.current = Math.min(text.length, before + Math.max(1, speed.current * dt));
        const crossed = text.slice(Math.floor(before), Math.floor(position.current));
        // Pause only at a comfortable pace; a big backlog just flows.
        if (speed.current < 600) {
          if (crossed.includes("\n\n")) holdUntil = now + PARAGRAPH_PAUSE_MS;
          else if (/[.!?:]\s/.test(crossed)) holdUntil = now + SENTENCE_PAUSE_MS;
        }
        setShown(wordEnd(text, Math.floor(position.current)));
      }
      schedule();
    };
    // A frame callback, with a timer in case frames stop (a hidden or undrawn page): whichever comes first.
    const schedule = () => {
      frame = requestAnimationFrame(tick);
      timer = window.setTimeout(tick, 50);
    };
    schedule();
    return () => { stopped = true; cancelAnimationFrame(frame); clearTimeout(timer); };
  }, [target.length, key]);

  // A reset shrinks the text under the cursor: never show past what exists.
  const count = Math.min(shown, target.length);
  return { text: target.slice(0, count), done: count >= target.length };
}
