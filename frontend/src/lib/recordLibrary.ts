/**
 * What is left of the reader's library in this browser: only deleting what
 * builds before the account library kept here.
 *
 * Saves and Reading status belong to the account as of IR-566 (ADR-044), the
 * reader's own folders as of IR-572 (ADR-070), both in `store/library.store.ts`,
 * and reading history as of IR-756, in `store/history.store.ts`.
 *
 * **The old browser copies are deleted, never read, uploaded or imported**
 * (ADR-044 amendments 2026-11-16): history in `iris_reading_history`, the
 * pre-IR-566 status folders and the reader's own folders in
 * `iris_record_collections`, and stars (Likes, retired by ADR-044 Q1) in
 * `iris_starred_records`. IRIS had no readers before the account library, so
 * nobody's work is in them, and reading them would hand one browser's data to
 * whoever signs in next.
 */

const OLD_LIBRARY_KEYS = ["iris_reading_history", "iris_record_collections", "iris_starred_records"] as const;

/**
 * Delete what an older build kept of the library in this browser. The auth
 * store calls it on every sign-in, sign-out and session end, so nothing of one
 * person's old library greets the next. Nothing writes these keys any more.
 */
export function clearOldBrowserLibrary(): void {
  for (const key of OLD_LIBRARY_KEYS) {
    try {
      localStorage.removeItem(key);
    } catch {
      /* storage unavailable: nothing was kept */
    }
  }
}
