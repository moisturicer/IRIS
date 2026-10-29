/**
 * NFR-S2 — the interface's half of the 30-minute inactivity rule (IR-166).
 *
 * The server decides when a session is idle (`apps/accounts/sessions.py`). It
 * cannot tell a click from a poll, so every request carries how long it has
 * been since the user last *did* something: `X-IRIS-Idle-Seconds`. A poll from
 * an untouched tab reports a large number and extends nothing.
 *
 * Only input counts: pointer, key, wheel, touch. `scroll` and `focus` do not,
 * because the page can cause both without the user.
 *
 * The interface also signs itself out on the same figure (`startIdleWatch`),
 * so a screen left open stops showing what it showed even if nothing on it
 * polls. Keep `IDLE_TIMEOUT_MS` equal to the server's
 * `SESSION_IDLE_TIMEOUT_MINUTES`.
 */

export const IDLE_HEADER = "X-IRIS-Idle-Seconds";
export const IDLE_TIMEOUT_MS = 30 * 60 * 1000;

const INPUT_EVENTS = ["pointerdown", "keydown", "wheel", "touchstart"] as const;
const CHECK_EVERY_MS = 30_000;

let lastInteraction = Date.now();

function markActive(): void {
  lastInteraction = Date.now();
}

/** Whole seconds since the user's last interaction. */
export function idleSeconds(): number {
  return Math.max(0, Math.floor((Date.now() - lastInteraction) / 1000));
}

/** Listen for input on `target`; returns the function that stops listening. */
export function trackActivity(target: Window = window): () => void {
  for (const type of INPUT_EVENTS) target.addEventListener(type, markActive, { passive: true, capture: true });
  return () => {
    for (const type of INPUT_EVENTS) target.removeEventListener(type, markActive, { capture: true });
  };
}

/** Call `onIdle` once, when the user has been idle for the timeout. */
export function startIdleWatch(onIdle: () => void): () => void {
  const timer = setInterval(() => {
    if (Date.now() - lastInteraction >= IDLE_TIMEOUT_MS) {
      clearInterval(timer);
      onIdle();
    }
  }, CHECK_EVERY_MS);
  return () => clearInterval(timer);
}

/** Test seam: the next test starts as if the page just loaded. */
export function __resetActivity(): void {
  lastInteraction = Date.now();
}
