/**
 * Whether this browser has been offered the Review workspace tour (IR-997).
 *
 * A per-viewer convenience, so it lives in `localStorage` and nowhere on the
 * server: no review data, permission or workflow state is touched. Storage can
 * be absent or throw (a private window, blocked site data); then the offer
 * simply shows again next visit, and the tour still works.
 */
const KEY = "iris-review-tour-seen";

export function tourSeen(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function markTourSeen(): void {
  try {
    localStorage.setItem(KEY, "1");
  } catch {
    /* The choice still applies for this visit. */
  }
}
