/**
 * What is left of the reader's library in this browser: only the wipe of the
 * old reading history.
 *
 * **Saves and Reading status belong to the account as of IR-566** (ADR-044),
 * **the reader's own folders as of IR-572** (ADR-070), both in
 * `store/library.store.ts`, **and reading history as of IR-756**, in
 * `store/history.store.ts`. What an older build kept in `iris_reading_history`
 * is never read or uploaded; it is deleted at the next sign-in, sign-out or
 * session end, so it is dropped, not imported (ADR-044 amendment 2026-11-16).
 *
 * **Old browser data is left untouched for IR-579's import.** Nothing here
 * reads or writes `iris_record_collections` (the pre-IR-566 status folders and
 * the reader's own folders) or `iris_starred_records` (Likes are retired,
 * ADR-044 Q1): reading them would hand one person's browser data to whoever
 * signs in next, the bug ADR-044 exists to fix.
 */

const HISTORY_KEY = "iris_reading_history";

/**
 * Delete what an older build kept of this browser's reading history. The auth
 * store calls it on every sign-in, sign-out and session end (ADR-044 Q2), so
 * the last person's copy never greets the next one. Nothing writes the key any
 * more.
 */
export function clearReadingHistory(): void {
  try {
    localStorage.removeItem(HISTORY_KEY);
  } catch {
    /* storage unavailable — nothing was kept */
  }
}
