/**
 * A decision in one of RDCO's queues changes the count beside it in the
 * sidebar (IR-1138). The pages that decide call `queueCountsChanged()` after a
 * success; the sidebar listens and reads the counts again, so the number
 * falls without a reload.
 */
const EVENT = "iris:queue-counts-changed";

export function queueCountsChanged(): void {
  window.dispatchEvent(new Event(EVENT));
}

/** Calls `onChange` on every decision; returns the unsubscribe. */
export function onQueueCountsChanged(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  return () => window.removeEventListener(EVENT, onChange);
}
