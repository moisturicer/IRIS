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

/**
 * The reader's account-backed library (IR-566). The owner is always the
 * signed-in account, so no call names one.
 */
export const libraryApi = {
  saves: () => apiClient.get<{ results: SavedRecordEntry[] }>("/library/saves/"),
  /** Omit `reading_status` to keep it; `null` clears it. Idempotent. */
  save: (recordId: number, body: { reading_status?: ReadingStatus | null } = {}) =>
    apiClient.put<SavedRecordEntry>(`/library/saves/${recordId}/`, body),
  /** Idempotent: 204 whether or not it was saved. */
  unsave: (recordId: number) => apiClient.delete(`/library/saves/${recordId}/`),
};
