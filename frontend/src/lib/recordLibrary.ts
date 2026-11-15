/**
 * The part of a reader's library that still lives in this browser.
 *
 * **Saves and Reading status belong to the account as of IR-566** (ADR-044),
 * **and the reader's own folders as of IR-572** (ADR-070): see
 * `store/library.store.ts`. What is left here is **reading history**,
 * browser-only and cleared on sign-out and on an account switch (ADR-044 Q2),
 * until IR-756 moves it to the account.
 *
 * **Old browser data is left untouched for IR-579's import.** Nothing here
 * reads or writes `iris_record_collections` (the pre-IR-566 status folders and
 * the reader's own folders) or `iris_starred_records` (Likes are retired,
 * ADR-044 Q1): reading them would hand one person's browser data to whoever
 * signs in next, the bug ADR-044 exists to fix.
 */

const HISTORY_KEY = "iris_reading_history";

/** How many visits to keep. Old entries fall off the end. */
const HISTORY_LIMIT = 50;

export interface ReadingVisit {
  recordId: number;
  /** Denormalised so history renders before the records resolve. */
  title: string;
  /** ISO timestamp of the most recent visit. */
  viewedAt: string;
}

/* ────────────────────────────────────────────────────────────────────────────
 * Storage primitives
 *
 * localStorage throws in private windows and embedded previews, and can hold
 * malformed JSON a previous version wrote. Neither may break a render.
 * ──────────────────────────────────────────────────────────────────────────*/

function readJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJSON(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable — in-memory state still updates for this session */
  }
}

/* ────────────────────────────────────────────────────────────────────────────
 * Reading history (browser-only; cleared on sign-out and account switch)
 *
 * The server keeps no reading history: it notes only an account's first opening
 * of a published paper, to count views (IR-369), and never returns it. So this
 * is written when the paper view opens.
 * It is genuinely this browser's history, and is labelled as such.
 * ──────────────────────────────────────────────────────────────────────────*/

export function getReadingHistory(): ReadingVisit[] {
  const value = readJSON<unknown>(HISTORY_KEY, []);
  if (!Array.isArray(value)) return [];
  return value.filter(
    (v): v is ReadingVisit =>
      Boolean(v) && typeof v.recordId === "number" && typeof v.viewedAt === "string",
  );
}

/** Record a visit, newest first, one entry per record. */
export function recordVisit(recordId: number, title: string): ReadingVisit[] {
  const next = [
    { recordId, title, viewedAt: new Date().toISOString() },
    ...getReadingHistory().filter((v) => v.recordId !== recordId),
  ].slice(0, HISTORY_LIMIT);
  writeJSON(HISTORY_KEY, next);
  return next;
}

/**
 * Forget this browser's history. Called by Clear history, and by the auth
 * store on every sign-in, sign-out and session end (ADR-044 Q2), so the next
 * person on a shared PC never sees what the last one opened.
 */
export function clearReadingHistory(): void {
  try {
    localStorage.removeItem(HISTORY_KEY);
  } catch {
    /* storage unavailable — nothing was kept */
  }
}
