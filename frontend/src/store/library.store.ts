import { create } from "zustand";

import { libraryApi, type ReadingStatus, type SavedRecordEntry } from "@/api/library";
import type { RecordListItem } from "@/types/records";

import { useAuthStore } from "./auth.store";

/**
 * The signed-in reader's saved Records and Reading status (IR-566, ADR-044 §6).
 *
 * One store, so Discover, the Record page and My Library can never disagree.
 * It belongs to one session:
 *
 * - **Cleared on every session change.** `sessionEpoch` moves on sign-in,
 *   sign-out and session end, so the next person on a shared PC starts empty.
 * - **Fenced.** Every request remembers the epoch it was made in; a response
 *   that lands after the epoch moved is dropped, never shown to the next
 *   account.
 * - **Optimistic, with a visible rollback.** A write shows at once; if the
 *   server refuses it, the previous state comes back and `failure` says so.
 *
 * Nothing here touches `localStorage` (ADR-044 §7).
 */

export const READING_STATUSES: { value: ReadingStatus; label: string; icon: string }[] = [
  { value: "want_to_read", label: "Want to read", icon: "fa-folder" },
  { value: "reading",      label: "Reading",      icon: "fa-folder-open" },
  { value: "completed",    label: "Completed",    icon: "fa-circle-check" },
];

export function readingStatusLabel(status: ReadingStatus): string {
  return READING_STATUSES.find((s) => s.value === status)?.label ?? status;
}

export interface LibraryItem {
  recordId:      number;
  /** False when the reader can no longer read the Record (ADR-044 §4). */
  available:     boolean;
  readingStatus: ReadingStatus | null;
  savedAt:       string;
  record?:       RecordListItem;
}

export interface LibraryFailure {
  recordId: number;
  message:  string;
}

type LoadState = "idle" | "loading" | "ready" | "error";

interface LibraryState {
  /** The epoch these items were loaded in; anything else is another session's. */
  epoch:   number;
  load:    LoadState;
  items:   Record<number, LibraryItem>;
  failure: LibraryFailure | null;

  ensureLoaded: (force?: boolean) => Promise<void>;
  /** Save a Record. Omit `readingStatus` to keep it; `null` clears it. */
  save:   (recordId: number, readingStatus?: ReadingStatus | null, record?: RecordListItem) => Promise<boolean>;
  unsave: (recordId: number) => Promise<boolean>;
  dismissFailure: () => void;
}

const empty = () => ({ load: "idle" as LoadState, items: {}, failure: null });

function toItem(entry: SavedRecordEntry): LibraryItem {
  if (!entry.available) {
    return { recordId: entry.record_id, available: false, readingStatus: null, savedAt: "" };
  }
  return {
    recordId:      entry.record_id,
    available:     true,
    readingStatus: entry.reading_status,
    savedAt:       entry.saved_at,
    record:        entry.record,
  };
}

const currentEpoch = () => useAuthStore.getState().sessionEpoch;

/** Per-Record write sequence: only the newest write's answer is applied. */
const writes = new Map<number, number>();
function nextWrite(recordId: number): number {
  const n = (writes.get(recordId) ?? 0) + 1;
  writes.set(recordId, n);
  return n;
}
const isLatest = (recordId: number, n: number) => writes.get(recordId) === n;

let inflightLoad: Promise<void> | null = null;

export const useLibraryStore = create<LibraryState>()((set, get) => ({
  epoch: currentEpoch(),
  ...empty(),

  ensureLoaded: async (force = false) => {
    if (!useAuthStore.getState().isAuthenticated) return;
    const { load } = get();
    if (!force && (load === "ready" || load === "loading")) return inflightLoad ?? undefined;

    const epoch = currentEpoch();
    set({ load: "loading", epoch });
    const request = libraryApi.saves().then(
      ({ data }) => {
        if (currentEpoch() !== epoch) return;
        const items: Record<number, LibraryItem> = {};
        for (const entry of data.results ?? []) items[entry.record_id] = toItem(entry);
        set({ items, load: "ready" });
      },
      () => {
        if (currentEpoch() !== epoch) return;
        set({ load: "error" });
      },
    );
    inflightLoad = request.finally(() => { inflightLoad = null; });
    return inflightLoad;
  },

  save: async (recordId, readingStatus, record) => {
    const epoch = currentEpoch();
    const n = nextWrite(recordId);
    const previous = get().items[recordId];
    const optimistic: LibraryItem = {
      recordId,
      available:     true,
      readingStatus: readingStatus === undefined ? previous?.readingStatus ?? null : readingStatus,
      savedAt:       previous?.savedAt || new Date().toISOString(),
      record:        record ?? previous?.record,
    };
    set((s) => ({ items: { ...s.items, [recordId]: optimistic }, failure: null }));

    try {
      const body = readingStatus === undefined ? {} : { reading_status: readingStatus };
      const { data } = await libraryApi.save(recordId, body);
      if (currentEpoch() !== epoch || !isLatest(recordId, n)) return true;
      set((s) => ({ items: { ...s.items, [recordId]: toItem(data) } }));
      return true;
    } catch {
      if (currentEpoch() !== epoch || !isLatest(recordId, n)) return false;
      set((s) => ({
        items: restore(s.items, recordId, previous),
        failure: { recordId, message: "Could not save this paper. Nothing was changed; try again." },
      }));
      return false;
    }
  },

  unsave: async (recordId) => {
    const epoch = currentEpoch();
    const n = nextWrite(recordId);
    const previous = get().items[recordId];
    set((s) => ({ items: restore(s.items, recordId, undefined), failure: null }));

    try {
      await libraryApi.unsave(recordId);
      return true;
    } catch {
      if (currentEpoch() !== epoch || !isLatest(recordId, n)) return false;
      set((s) => ({
        items: restore(s.items, recordId, previous),
        failure: { recordId, message: "Could not remove this paper. It is still saved; try again." },
      }));
      return false;
    }
  },

  dismissFailure: () => set({ failure: null }),
}));

function restore(
  items: Record<number, LibraryItem>,
  recordId: number,
  value: LibraryItem | undefined,
): Record<number, LibraryItem> {
  const next = { ...items };
  if (value) next[recordId] = value;
  else delete next[recordId];
  return next;
}

/** Saved items, newest first. */
export function sortedItems(items: Record<number, LibraryItem>): LibraryItem[] {
  return Object.values(items).sort((a, b) => b.savedAt.localeCompare(a.savedAt));
}

/**
 * A new session starts with an empty library. Subscribing here keeps the auth
 * store from having to know this one exists (the IR-746 pattern).
 */
useAuthStore.subscribe((state, previous) => {
  if (state.sessionEpoch !== previous.sessionEpoch) {
    writes.clear();
    inflightLoad = null;
    useLibraryStore.setState({ epoch: state.sessionEpoch, ...empty() });
  }
});
