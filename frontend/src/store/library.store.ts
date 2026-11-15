import { create } from "zustand";

import { isRequestTimeout } from "@/api/requestPolicy";
import { libraryApi, type FolderEntry, type ReadingStatus, type SavedRecordEntry } from "@/api/library";
import type { RecordListItem } from "@/types/records";

import { useAuthStore } from "./auth.store";

/**
 * The signed-in reader's saved Records, Reading status (IR-566, ADR-044 §6)
 * and own folders (IR-572, ADR-070).
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
 *   Creating a folder is the one exception: it waits for the server, which
 *   names the folder, then shows it.
 *
 * A folder holds saved papers, as the server does: filing an unsaved paper
 * shows it saved, and unsaving takes it out of every folder. Taking a paper
 * out of a folder never unsaves it.
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

/** The server's bound on a folder's name (`apps/library` MAX_FOLDER_NAME): change both together. */
export const MAX_FOLDER_NAME = 60;

/** One of the reader's own folders: the saved Records filed in it, newest first. */
export interface LibraryFolder {
  id:        number;
  name:      string;
  recordIds: number[];
}

export interface LibraryFailure {
  /** The paper the failed write was about; null for a folder's own rename or delete. */
  recordId: number | null;
  message:  string;
}

type LoadState = "idle" | "loading" | "ready" | "error";

interface LibraryState {
  /** The epoch these items were loaded in; anything else is another session's. */
  epoch:   number;
  load:    LoadState;
  /** `load` is `error` because the read timed out, not because it was refused (IR-906). */
  interrupted: boolean;
  items:   Record<number, LibraryItem>;
  /** The reader's own folders, oldest first, as the server lists them. */
  folders: LibraryFolder[];
  /** How many folders the account may hold; the server says (IR-572). */
  folderLimit: number | null;
  failure: LibraryFailure | null;

  ensureLoaded: (force?: boolean) => Promise<void>;
  /** Save a Record. Omit `readingStatus` to keep it; `null` clears it. */
  save:   (recordId: number, readingStatus?: ReadingStatus | null, record?: RecordListItem) => Promise<boolean>;
  unsave: (recordId: number) => Promise<boolean>;
  /**
   * The folder the server made, or the one already named so; null if refused.
   * `forRecord` is the paper the reader is filing, so a refusal shows beside it.
   */
  createFolder: (name: string, forRecord?: number) => Promise<LibraryFolder | null>;
  renameFolder: (folderId: number, name: string) => Promise<boolean>;
  deleteFolder: (folderId: number) => Promise<boolean>;
  /** File a Record in a folder, saving it if it was not saved. */
  fileInFolder: (folderId: number, recordId: number, record?: RecordListItem) => Promise<boolean>;
  /** Take a Record out of one folder. It stays saved. */
  removeFromFolder: (folderId: number, recordId: number) => Promise<boolean>;
  dismissFailure: () => void;
}

const empty = () => ({
  load: "idle" as LoadState, interrupted: false, items: {}, folders: [], folderLimit: null, failure: null,
});

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

function toFolder(entry: FolderEntry): LibraryFolder {
  return { id: entry.id, name: entry.name, recordIds: Array.isArray(entry.record_ids) ? entry.record_ids : [] };
}

/** Does the account hold the most folders it may? Unknown until the server says. */
export function atFolderLimit(folders: LibraryFolder[], limit: number | null): boolean {
  return limit !== null && folders.length >= limit;
}

const currentEpoch = () => useAuthStore.getState().sessionEpoch;

/**
 * Per-subject write sequence: only the newest write's answer is applied. A
 * subject is a paper's save (`record:5`), a folder (`folder:3`) or one paper's
 * place in one folder (`filing:3:5`).
 */
const writes = new Map<string, number>();
function nextWrite(key: string): number {
  const n = (writes.get(key) ?? 0) + 1;
  writes.set(key, n);
  return n;
}
const isLatest = (key: string, n: number) => writes.get(key) === n;
const saveKey = (recordId: number) => `record:${recordId}`;
const folderKey = (folderId: number) => `folder:${folderId}`;
const filingKey = (folderId: number, recordId: number) => `filing:${folderId}:${recordId}`;

/** The server's words for a refused folder write, when it gave some. */
function refusal(error: unknown, fallback: string): string {
  const response = (error as { response?: { status?: number; data?: Record<string, unknown> } })?.response;
  if (response?.status !== 400 || !response.data) return fallback;
  const { detail, name } = response.data;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(name) && typeof name[0] === "string") return name[0];
  return fallback;
}

let inflightLoad: Promise<void> | null = null;

export const useLibraryStore = create<LibraryState>()((set, get) => {
  /** Put `folder` back as the server described it, or add it at the end. */
  const placeFolder = (folder: LibraryFolder) => set((s) => ({
    folders: s.folders.some((f) => f.id === folder.id)
      ? s.folders.map((f) => (f.id === folder.id ? folder : f))
      : [...s.folders, folder],
  }));
  /** File `recordId` in `folderId` at position `at` (first, as a new filing is), or take it out. */
  const withFiling = (folderId: number, recordId: number, filed: boolean, at = 0) => set((s) => ({
    folders: s.folders.map((f) => {
      if (f.id !== folderId) return f;
      const rest = f.recordIds.filter((id) => id !== recordId);
      if (filed) rest.splice(Math.min(at, rest.length), 0, recordId);
      return { ...f, recordIds: rest };
    }),
  }));
  /** Where `recordId` sits in each folder holding it, so a rollback puts it back there. */
  const placesOf = (recordId: number) => get().folders.flatMap((f) => {
    const at = f.recordIds.indexOf(recordId);
    return at < 0 ? [] : [{ folderId: f.id, at }];
  });

  return {
    epoch: currentEpoch(),
    ...empty(),

    ensureLoaded: async (force = false) => {
      if (!useAuthStore.getState().isAuthenticated) return;
      const { load } = get();
      if (!force && (load === "ready" || load === "loading")) return inflightLoad ?? undefined;

      const epoch = currentEpoch();
      set({ load: "loading", interrupted: false, epoch });
      // Saves and folders are one library: a reader is never shown their saves
      // with their folders quietly missing.
      const request = Promise.all([libraryApi.saves(), libraryApi.folders()]).then(
        ([{ data: saved }, { data: own }]) => {
          if (currentEpoch() !== epoch) return;
          const items: Record<number, LibraryItem> = {};
          for (const entry of saved.results ?? []) items[entry.record_id] = toItem(entry);
          set({ items, folders: (own.results ?? []).map(toFolder), folderLimit: own.limit ?? null, load: "ready" });
        },
        (error: unknown) => {
          if (currentEpoch() !== epoch) return;
          set({ load: "error", interrupted: isRequestTimeout(error) });
        },
      );
      inflightLoad = request.finally(() => { inflightLoad = null; });
      return inflightLoad;
    },

    save: async (recordId, readingStatus, record) => {
      const epoch = currentEpoch();
      const key = saveKey(recordId);
      const n = nextWrite(key);
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
        if (currentEpoch() !== epoch || !isLatest(key, n)) return true;
        set((s) => ({ items: { ...s.items, [recordId]: toItem(data) } }));
        return true;
      } catch {
        if (currentEpoch() !== epoch || !isLatest(key, n)) return false;
        set((s) => ({
          items: restore(s.items, recordId, previous),
          failure: { recordId, message: "Could not save this paper. Nothing was changed; try again." },
        }));
        return false;
      }
    },

    unsave: async (recordId) => {
      const epoch = currentEpoch();
      const key = saveKey(recordId);
      const n = nextWrite(key);
      const previous = get().items[recordId];
      // Unsaving takes the paper out of every folder, as the server does.
      const places = placesOf(recordId);
      set((s) => ({
        items: restore(s.items, recordId, undefined),
        folders: s.folders.map((f) => ({ ...f, recordIds: f.recordIds.filter((id) => id !== recordId) })),
        failure: null,
      }));

      try {
        await libraryApi.unsave(recordId);
        return true;
      } catch {
        if (currentEpoch() !== epoch || !isLatest(key, n)) return false;
        set((s) => ({ items: restore(s.items, recordId, previous) }));
        places.forEach(({ folderId, at }) => withFiling(folderId, recordId, true, at));
        set({ failure: { recordId, message: "Could not remove this paper. It is still saved; try again." } });
        return false;
      }
    },

    createFolder: async (name, forRecord) => {
      const epoch = currentEpoch();
      set({ failure: null });
      try {
        const { data } = await libraryApi.createFolder(name);
        if (currentEpoch() !== epoch) return null;
        const folder = toFolder(data);
        placeFolder(folder);
        return folder;
      } catch (error) {
        if (currentEpoch() !== epoch) return null;
        set({
          failure: {
            recordId: forRecord ?? null,
            message: refusal(error, "Could not create this folder. Nothing was changed; try again."),
          },
        });
        return null;
      }
    },

    renameFolder: async (folderId, name) => {
      const epoch = currentEpoch();
      const key = folderKey(folderId);
      const n = nextWrite(key);
      const previous = get().folders.find((f) => f.id === folderId);
      if (!previous) return false;
      set((s) => ({ folders: s.folders.map((f) => (f.id === folderId ? { ...f, name } : f)), failure: null }));

      try {
        const { data } = await libraryApi.renameFolder(folderId, name);
        if (currentEpoch() !== epoch || !isLatest(key, n)) return true;
        set((s) => ({ folders: s.folders.map((f) => (f.id === folderId ? { ...f, name: data.name } : f)) }));
        return true;
      } catch (error) {
        if (currentEpoch() !== epoch || !isLatest(key, n)) return false;
        set((s) => ({
          folders: s.folders.map((f) => (f.id === folderId ? { ...f, name: previous.name } : f)),
          failure: { recordId: null, message: refusal(error, "Could not rename this folder. Its name is unchanged; try again.") },
        }));
        return false;
      }
    },

    deleteFolder: async (folderId) => {
      const epoch = currentEpoch();
      const key = folderKey(folderId);
      const n = nextWrite(key);
      const index = get().folders.findIndex((f) => f.id === folderId);
      if (index < 0) return true;
      const previous = get().folders[index];
      set((s) => ({ folders: s.folders.filter((f) => f.id !== folderId), failure: null }));

      try {
        await libraryApi.deleteFolder(folderId);
        return true;
      } catch {
        if (currentEpoch() !== epoch || !isLatest(key, n)) return false;
        set((s) => {
          const folders = s.folders.filter((f) => f.id !== folderId);
          folders.splice(Math.min(index, folders.length), 0, previous);
          return { folders, failure: { recordId: null, message: "Could not delete this folder. It is still there; try again." } };
        });
        return false;
      }
    },

    fileInFolder: async (folderId, recordId, record) => {
      const epoch = currentEpoch();
      const key = filingKey(folderId, recordId);
      const n = nextWrite(key);
      const wasFiled = get().folders.find((f) => f.id === folderId)?.recordIds.includes(recordId) ?? false;
      // A folder holds saved papers: filing an unsaved one saves it too, and
      // counts as a write to that save.
      const saving = get().items[recordId] === undefined;
      const saveWrite = saving ? nextWrite(saveKey(recordId)) : writes.get(saveKey(recordId)) ?? 0;
      /** No save, status change or unsave of this paper began after the filing. */
      const saveUntouched = () => (writes.get(saveKey(recordId)) ?? 0) === saveWrite;
      withFiling(folderId, recordId, true);
      if (saving) {
        set((s) => ({
          items: {
            ...s.items,
            [recordId]: { recordId, available: true, readingStatus: null, savedAt: new Date().toISOString(), record },
          },
        }));
      }
      set({ failure: null });

      try {
        const { data } = await libraryApi.fileInFolder(folderId, recordId);
        if (currentEpoch() !== epoch) return true;
        // The answer's save is as of the filing: a newer write to it wins.
        if (saveUntouched()) set((s) => ({ items: { ...s.items, [recordId]: toItem(data.save) } }));
        if (isLatest(key, n)) {
          const folder = toFolder(data.folder);
          // A newer unsave took the paper out of every folder; keep it out.
          const stillSaved = get().items[recordId] !== undefined;
          placeFolder(stillSaved ? folder : { ...folder, recordIds: folder.recordIds.filter((id) => id !== recordId) });
        }
        return true;
      } catch {
        if (currentEpoch() !== epoch || !isLatest(key, n)) return false;
        if (!wasFiled) withFiling(folderId, recordId, false);
        if (saving && saveUntouched()) {
          set((s) => ({ items: restore(s.items, recordId, undefined) }));
        }
        set({ failure: { recordId, message: "Could not add this paper to the folder. Nothing was changed; try again." } });
        return false;
      }
    },

    removeFromFolder: async (folderId, recordId) => {
      const epoch = currentEpoch();
      const key = filingKey(folderId, recordId);
      const n = nextWrite(key);
      const place = placesOf(recordId).find((p) => p.folderId === folderId);
      withFiling(folderId, recordId, false);
      set({ failure: null });

      try {
        await libraryApi.removeFromFolder(folderId, recordId);
        return true;
      } catch {
        if (currentEpoch() !== epoch || !isLatest(key, n)) return false;
        if (place) withFiling(folderId, recordId, true, place.at);
        set({ failure: { recordId, message: "Could not take this paper out of the folder. It is still in the folder; try again." } });
        return false;
      }
    },

    dismissFailure: () => set({ failure: null }),
  };
});

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
