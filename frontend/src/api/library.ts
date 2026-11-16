import { apiClient } from "./client";
import type { PageRegion, RecordListItem } from "@/types/records";

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

/**
 * One of the reader's own folders (IR-572, ADR-070). `record_ids` are the saved
 * Records filed in it, newest filing first. Every one is also a save, so its
 * paper (or `available: false`) comes from the saves list, never from here.
 */
export interface FolderEntry {
  id:         number;
  name:       string;
  record_ids: number[];
  created_at: string;
  updated_at: string;
}

/** What filing a Record answers: the folder, and the save filing made or kept. */
export interface FilingEntry {
  folder: FolderEntry;
  save:   SavedRecordEntry;
}

/** The keys of a saved feed's query: exactly the ones Discover writes into its URL. */
export type FeedQueryKey = "q" | "type" | "college" | "classification" | "year_from" | "year_to" | "ip" | "sort";
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
 * One of the reader's highlights (IR-583, ADR-065). `stale` means the Manuscript
 * the reader is served is no longer the one it was made on: it is shown as the
 * passage it was and never drawn on the new paper. `open_version` is the Version
 * that still holds a stale highlight's bytes. One whose Record the reader can no
 * longer read carries nothing but the ids they supplied.
 */
export type HighlightEntry =
  | {
      id:           number;
      record_id:    number;
      available:    true;
      state:        "current" | "stale";
      page:         number;
      quote:        string;
      prefix:       string;
      suffix:       string;
      regions:      PageRegion[];
      open_version: number | null;
      created_at:   string;
    }
  | { id: number; record_id: number; available: false };

/**
 * One paper in the reader's history (IR-756). One they can no longer read
 * carries only its id (ADR-044 §Amendment 2026-11-01, point 4).
 */
export type ReadingHistoryEntry =
  | { record_id: number; available: true; viewed_at: string; record: RecordListItem }
  | { record_id: number; available: false };

/** The reader's library settings (IR-756). `keep_history` false pauses history. */
export interface LibraryPreferences {
  keep_history: boolean;
}

/** What a highlight is saved from: the passage, and the revision the paper was opened at. */
export interface HighlightDraft {
  manuscript_revision: string;
  page:    number;
  quote:   string;
  prefix:  string;
  suffix:  string;
  regions: PageRegion[];
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

  /** The reader's highlights on one Record. A Record they cannot read is a 404. */
  highlights: (recordId: number) =>
    apiClient.get<{ results: HighlightEntry[] }>(`/library/highlights/${recordId}/`),
  /**
   * Save a passage. A 409 `manuscript_changed` means the paper was replaced since
   * it was opened; nothing is stored. Saving the same passage again returns it.
   */
  saveHighlight: (recordId: number, body: HighlightDraft) =>
    apiClient.post<HighlightEntry>(`/library/highlights/${recordId}/`, body),
  /** Idempotent: 204 whether or not it was there. */
  deleteHighlight: (recordId: number, highlightId: number) =>
    apiClient.delete(`/library/highlights/${recordId}/${highlightId}/`),

  saves: () => apiClient.get<{ results: SavedRecordEntry[] }>("/library/saves/"),
  /** Omit `reading_status` to keep it; `null` clears it. Idempotent. */
  save: (recordId: number, body: { reading_status?: ReadingStatus | null } = {}) =>
    apiClient.put<SavedRecordEntry>(`/library/saves/${recordId}/`, body),
  /** Idempotent: 204 whether or not it was saved. */
  unsave: (recordId: number) => apiClient.delete(`/library/saves/${recordId}/`),

  /** The reader's own folders, oldest first, with the account limit (IR-572). */
  folders: () => apiClient.get<{ results: FolderEntry[]; limit: number }>("/library/folders/"),
  /** Creating a name the reader already has, ignoring case, returns that folder. */
  createFolder: (name: string) => apiClient.post<FolderEntry>("/library/folders/", { name }),
  renameFolder: (folderId: number, name: string) =>
    apiClient.patch<FolderEntry>(`/library/folders/${folderId}/`, { name }),
  /** Idempotent: 204 whether or not it was there. Never deletes a save. */
  deleteFolder: (folderId: number) => apiClient.delete(`/library/folders/${folderId}/`),
  /** Saves the Record if it was not saved. Idempotent. */
  fileInFolder: (folderId: number, recordId: number) =>
    apiClient.put<FilingEntry>(`/library/folders/${folderId}/records/${recordId}/`),
  /** Idempotent: 204 whether or not it was filed. Never unsaves. */
  removeFromFolder: (folderId: number, recordId: number) =>
    apiClient.delete(`/library/folders/${folderId}/records/${recordId}/`),

  /** The reader's saved feeds, with the account limit (IR-577). */
  feeds: () => apiClient.get<{ results: SavedFeed[]; limit: number }>("/library/feeds/"),
  createFeed: (body: { name: string; query: FeedQuery }) =>
    apiClient.post<SavedFeed>("/library/feeds/", body),
  /** Rename it, replace its criteria, or both. Renaming leaves the criteria alone. */
  updateFeed: (id: number, body: { name?: string; query?: FeedQuery }) =>
    apiClient.patch<SavedFeed>(`/library/feeds/${id}/`, body),
  deleteFeed: (id: number) => apiClient.delete(`/library/feeds/${id}/`),

  /** The papers the reader opened, most recent first, at most 50 (IR-756). */
  history: () => apiClient.get<{ results: ReadingHistoryEntry[] }>("/library/history/"),
  /**
   * The paper view says the reader opened this Record. Idempotent; a 404 for a
   * Record they cannot read. While history is paused it is a 204 that records nothing.
   */
  visit: (recordId: number) => apiClient.put(`/library/history/${recordId}/`, {}),
  /** Clear history: the server deletes every entry. */
  clearHistory: () => apiClient.delete("/library/history/"),
  /** The reader's settings; the defaults when they never changed one. */
  preferences: () => apiClient.get<LibraryPreferences>("/library/preferences/"),
  updatePreferences: (body: LibraryPreferences) =>
    apiClient.patch<LibraryPreferences>("/library/preferences/", body),
};
