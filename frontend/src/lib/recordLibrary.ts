/**
 * The parts of a reader's library that still live in this browser.
 *
 * **Saves and Reading status belong to the account as of IR-566** (ADR-044):
 * see `store/library.store.ts`. What is left here is:
 *
 * - **The reader's own folders**, browser-only until IR-572, and labelled so.
 * - **The wipe of the old reading history.** History follows the account as
 *   of IR-756 (`store/history.store.ts`). What an older build kept in
 *   `iris_reading_history` is never read or uploaded; it is deleted at the next
 *   sign-in, sign-out or session end.
 *
 * **Old browser data is left untouched for IR-579's import.** The three
 * reading-status folders inside `iris_record_collections`, and every star in
 * `iris_starred_records` (Likes are retired, ADR-044 Q1), are never read here:
 * reading them would hand one person's browser data to whoever signs in next,
 * the bug ADR-044 exists to fix. Writing own folders preserves those entries
 * byte-for-byte.
 */

const COLLECTIONS_KEY = "iris_record_collections";
const HISTORY_KEY = "iris_reading_history";

export interface Collection {
  id: string;
  name: string;
  recordIds: number[];
}

/**
 * Ids the pre-IR-566 status folders used inside `iris_record_collections`.
 * Kept only so own-folder reads skip them and writes preserve them.
 */
const LEGACY_STATUS_FOLDER_IDS = ["want-to-read", "reading", "completed"];

function isLegacyStatusFolder(id: unknown): boolean {
  return typeof id === "string" && LEGACY_STATUS_FOLDER_IDS.includes(id);
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
 * The reader's own folders (browser-only until IR-572)
 * ──────────────────────────────────────────────────────────────────────────*/

function isCollection(c: unknown): c is Collection {
  const value = c as Collection | null;
  return Boolean(value) && typeof value!.id === "string" && typeof value!.name === "string" && Array.isArray(value!.recordIds);
}

/** The reader's own folders, in the order they made them. */
export function getCollections(): Collection[] {
  const stored = readJSON<unknown>(COLLECTIONS_KEY, null);
  if (!Array.isArray(stored)) return [];
  return stored.filter(isCollection).filter((c) => !isLegacyStatusFolder(c.id));
}

/**
 * Store the reader's own folders. Every entry this module does not own -- the
 * legacy status folders, or anything malformed -- is written back unchanged,
 * in place, so IR-579 finds exactly what was there.
 */
export function saveCollections(collections: Collection[]): void {
  const stored = readJSON<unknown>(COLLECTIONS_KEY, null);
  const preserved = Array.isArray(stored)
    ? stored.filter((c) => !isCollection(c) || isLegacyStatusFolder(c.id))
    : [];
  writeJSON(COLLECTIONS_KEY, [...preserved, ...collections]);
}

/** Add or remove a record from one of the reader's own folders. */
export function toggleRecordInCollection(
  collections: Collection[],
  collectionId: string,
  recordId: number,
): Collection[] {
  const target = collections.find((c) => c.id === collectionId);
  if (!target) return collections;
  const adding = !target.recordIds.includes(recordId);

  const next = collections.map((collection) =>
    collection.id === collectionId
      ? {
          ...collection,
          recordIds: adding
            ? [...collection.recordIds, recordId]
            : collection.recordIds.filter((id) => id !== recordId),
        }
      : collection,
  );
  saveCollections(next);
  return next;
}

export function addCollection(collections: Collection[], name: string): Collection[] {
  const trimmed = name.trim();
  if (!trimmed) return collections;
  const next = [...collections, { id: `${Date.now()}`, name: trimmed, recordIds: [] as number[] }];
  saveCollections(next);
  return next;
}

export function renameCollection(
  collections: Collection[],
  collectionId: string,
  name: string,
): Collection[] {
  const trimmed = name.trim();
  if (!trimmed) return collections;
  const next = collections.map((c) => (c.id === collectionId ? { ...c, name: trimmed } : c));
  saveCollections(next);
  return next;
}

export function deleteCollection(collections: Collection[], collectionId: string): Collection[] {
  const next = collections.filter((c) => c.id !== collectionId);
  saveCollections(next);
  return next;
}

/** Take records out of one folder, or out of every folder when no id is given. */
export function removeFromCollections(
  collections: Collection[],
  recordIds: number[],
  collectionId?: string,
): Collection[] {
  const drop = new Set(recordIds);
  const next = collections.map((c) =>
    collectionId && c.id !== collectionId
      ? c
      : { ...c, recordIds: c.recordIds.filter((id) => !drop.has(id)) },
  );
  saveCollections(next);
  return next;
}

/* ────────────────────────────────────────────────────────────────────────────
 * The old browser reading history (written before IR-756; never read now)
 * ──────────────────────────────────────────────────────────────────────────*/

/**
 * Delete what an older build kept of this browser's reading history. The auth
 * store calls it on every sign-in, sign-out and session end (ADR-044 Q2), so
 * the last person's copy never greets the next one. Nothing writes the key any
 * more: history is on the account (IR-756), and this copy is dropped, not
 * imported (owner's decision, 2026-11-16).
 */
export function clearReadingHistory(): void {
  try {
    localStorage.removeItem(HISTORY_KEY);
  } catch {
    /* storage unavailable — nothing was kept */
  }
}
