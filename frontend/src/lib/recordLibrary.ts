/**
 * Per-browser record library — starred papers, folders, and reading history.
 *
 * IRIS has **no server-side bookmark model**. `apps/storage` stores uploaded
 * files in folders; it is not a reading list, and it is slated for removal.
 * So everything here persists to this browser's localStorage and never syncs.
 * Every surface that reads it must say so rather than implying an account-level
 * library.
 *
 * This module is the single owner of that state. `features/discover/discoverUtils`
 * re-exports it so the Discover save-dropdown and My Library cannot drift apart.
 */

const STARRED_KEY = "iris_starred_records";
const COLLECTIONS_KEY = "iris_record_collections";
const HISTORY_KEY = "iris_reading_history";

/** How many visits to keep. Old entries fall off the end. */
const HISTORY_LIMIT = 50;

export interface Collection {
  id: string;
  name: string;
  recordIds: number[];
}

export interface ReadingVisit {
  recordId: number;
  /** Denormalised so history renders before the records resolve. */
  title: string;
  /** ISO timestamp of the most recent visit. */
  viewedAt: string;
}

/**
 * The three reading-status folders.
 *
 * A record has at most one status — it cannot be both unread and finished — so
 * these are mutually exclusive, and `toggleRecordInCollection` enforces that.
 * Custom topic folders are additive: a paper can sit in as many as you like.
 */
export const STATUS_FOLDER_IDS = ["want-to-read", "reading", "completed"] as const;
export type StatusFolderId = (typeof STATUS_FOLDER_IDS)[number];

export const STATUS_FOLDER_ICONS: Record<StatusFolderId, string> = {
  "want-to-read": "fa-folder",
  reading: "fa-folder-open",
  completed: "fa-circle-check",
};

export const DEFAULT_COLLECTIONS: Collection[] = [
  { id: "want-to-read", name: "Want to read", recordIds: [] },
  { id: "reading", name: "Reading", recordIds: [] },
  { id: "completed", name: "Completed", recordIds: [] },
];

export function isStatusFolder(id: string): id is StatusFolderId {
  return (STATUS_FOLDER_IDS as readonly string[]).includes(id);
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
 * Starred ("liked") papers
 * ──────────────────────────────────────────────────────────────────────────*/

export function getStarredIds(): number[] {
  const value = readJSON<unknown>(STARRED_KEY, []);
  return Array.isArray(value) ? value.filter((id): id is number => typeof id === "number") : [];
}

export function isStarred(recordId: number): boolean {
  return getStarredIds().includes(recordId);
}

/** Toggle and return the new starred state. */
export function toggleStarred(recordId: number): boolean {
  const current = getStarredIds();
  const next = current.includes(recordId)
    ? current.filter((id) => id !== recordId)
    : [...current, recordId];
  writeJSON(STARRED_KEY, next);
  return next.includes(recordId);
}

/* ────────────────────────────────────────────────────────────────────────────
 * Folders
 * ──────────────────────────────────────────────────────────────────────────*/

/**
 * Stored folders, with the three status folders guaranteed present and first.
 * A user who saved papers under an older default set keeps those folders — they
 * just move below the status ones.
 */
export function getCollections(): Collection[] {
  const stored = readJSON<Collection[] | null>(COLLECTIONS_KEY, null);
  if (!Array.isArray(stored) || stored.length === 0) return DEFAULT_COLLECTIONS;

  const valid = stored.filter(
    (c): c is Collection =>
      Boolean(c) && typeof c.id === "string" && typeof c.name === "string" && Array.isArray(c.recordIds),
  );

  const missing = DEFAULT_COLLECTIONS.filter((d) => !valid.some((c) => c.id === d.id));
  const merged = [...valid, ...missing];

  return [
    ...STATUS_FOLDER_IDS.map((id) => merged.find((c) => c.id === id)!).filter(Boolean),
    ...merged.filter((c) => !isStatusFolder(c.id)),
  ];
}

export function saveCollections(collections: Collection[]): void {
  writeJSON(COLLECTIONS_KEY, collections);
}

/** Folders holding this record, in display order. */
export function collectionsFor(collections: Collection[], recordId: number): Collection[] {
  return collections.filter((c) => c.recordIds.includes(recordId));
}

/**
 * Add or remove a record from a folder.
 *
 * Adding it to a *status* folder removes it from the other two, because the
 * three describe one reading state. Topic folders are unaffected either way.
 */
export function toggleRecordInCollection(
  collections: Collection[],
  collectionId: string,
  recordId: number,
): Collection[] {
  const target = collections.find((c) => c.id === collectionId);
  if (!target) return collections;

  const adding = !target.recordIds.includes(recordId);
  const exclusive = adding && isStatusFolder(collectionId);

  const next = collections.map((collection) => {
    if (collection.id === collectionId) {
      return {
        ...collection,
        recordIds: adding
          ? [...collection.recordIds, recordId]
          : collection.recordIds.filter((id) => id !== recordId),
      };
    }
    if (exclusive && isStatusFolder(collection.id)) {
      return { ...collection, recordIds: collection.recordIds.filter((id) => id !== recordId) };
    }
    return collection;
  });

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

/** Status folders are part of the model, so only topic folders can be removed. */
export function deleteCollection(collections: Collection[], collectionId: string): Collection[] {
  if (isStatusFolder(collectionId)) return collections;
  const next = collections.filter((c) => c.id !== collectionId);
  saveCollections(next);
  return next;
}

/** Drop a record from every folder — "remove from library". */
export function removeFromAllCollections(
  collections: Collection[],
  recordIds: number[],
): Collection[] {
  const drop = new Set(recordIds);
  const next = collections.map((c) => ({
    ...c,
    recordIds: c.recordIds.filter((id) => !drop.has(id)),
  }));
  saveCollections(next);
  return next;
}

/* ────────────────────────────────────────────────────────────────────────────
 * Reading history
 *
 * Nothing server-side records who read what — `Record.access_count` is a global
 * counter, not a per-user log — so this is written when the paper view opens.
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

export function clearReadingHistory(): void {
  writeJSON(HISTORY_KEY, []);
}
