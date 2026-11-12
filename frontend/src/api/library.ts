import { apiClient } from "./client";
import type { RecordListItem } from "@/types/records";

/** `core.enums.ReadingStatus` (IR-566, ADR-044 §2). */
export type ReadingStatus = "want_to_read" | "reading" | "completed";

/**
 * One saved Record. A save whose Record the reader can no longer read carries
 * only the id they supplied (ADR-044 §4).
 */
export type SavedRecordEntry =
  | {
      record_id:      number;
      available:      true;
      reading_status: ReadingStatus | null;
      saved_at:       string;
      updated_at:     string;
      record:         RecordListItem;
    }
  | { record_id: number; available: false };

/** The keys of a saved feed's query: exactly the ones Discover writes into its URL. */
export type FeedQueryKey = "q" | "type" | "college" | "classification" | "year" | "ip" | "sort";
export type FeedQuery = Partial<Record<FeedQueryKey, string>>;
/** Taxonomy ids a saved feed names that no longer exist, by key (IR-577). */
export type FeedStale = Partial<Record<"type" | "college" | "classification", number[]>>;

/**
 * One private custom feed (IR-577): Discover's own query under a name. `stale`
 * is reported, never repaired: the stored `query` still names the lost values,
 * so nothing widens by itself.
 */
export interface SavedFeed {
  id:         number;
  name:       string;
  query:      FeedQuery;
  stale:      FeedStale;
  created_at: string;
  updated_at: string;
}

/**
 * The reader's private note on one Record (IR-580, ADR-064). `revision` is 0
 * for a Record they have not written on yet; a write names the revision it
 * started from.
 */
export interface ReadingNote {
  body:       string;
  revision:   number;
  updated_at: string | null;
}

/**
 * The reader's account-backed library (IR-566). The owner is always the
 * signed-in account, so no call names one.
 */
export const libraryApi = {
  /** The reader's note, or an empty one at revision 0. Reading creates nothing. */
  note: (recordId: number) => apiClient.get<ReadingNote>(`/library/notes/${recordId}/`),
  /**
   * Stored only if `base_revision` is the stored revision. Otherwise a 409 whose
   * body is the server's current note, and nothing is written.
   */
  saveNote: (recordId: number, body: { body: string; base_revision: number }) =>
    apiClient.put<ReadingNote>(`/library/notes/${recordId}/`, body),

  saves: () => apiClient.get<{ results: SavedRecordEntry[] }>("/library/saves/"),
  /** Omit `reading_status` to keep it; `null` clears it. Idempotent. */
  save: (recordId: number, body: { reading_status?: ReadingStatus | null } = {}) =>
    apiClient.put<SavedRecordEntry>(`/library/saves/${recordId}/`, body),
  /** Idempotent: 204 whether or not it was saved. */
  unsave: (recordId: number) => apiClient.delete(`/library/saves/${recordId}/`),

  /** The reader's saved feeds, with the account limit (IR-577). */
  feeds: () => apiClient.get<{ results: SavedFeed[]; limit: number }>("/library/feeds/"),
  createFeed: (body: { name: string; query: FeedQuery }) =>
    apiClient.post<SavedFeed>("/library/feeds/", body),
  /** Rename it, replace its criteria, or both. Renaming leaves the criteria alone. */
  updateFeed: (id: number, body: { name?: string; query?: FeedQuery }) =>
    apiClient.patch<SavedFeed>(`/library/feeds/${id}/`, body),
  deleteFeed: (id: number) => apiClient.delete(`/library/feeds/${id}/`),
};
