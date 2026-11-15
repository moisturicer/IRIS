import { create } from "zustand";

import { isRequestTimeout } from "@/api/requestPolicy";
import { libraryApi, type ReadingHistoryEntry } from "@/api/library";
import type { RecordListItem } from "@/types/records";

import { useAuthStore } from "./auth.store";

/**
 * The signed-in reader's reading history (IR-756, ADR-044 §Amendment 2026-11-01).
 *
 * History lives on the account: the paper view tells the server a Record was
 * opened, and My Library reads the list back, so a paper opened on a lab PC is
 * there at home. Only the reader can see it. Like the library store it belongs
 * to one session:
 *
 * - **Cleared on every session change**, and every answer is fenced by the
 *   epoch it was asked in, so the next person on a shared PC never sees the
 *   last one's history or inherits their pause.
 * - **Pausing is the reader's.** While history is paused the paper view sends
 *   no visit, asking the setting again on each paper so a resume elsewhere is
 *   seen; the server refuses to record anyway, so a second device that has not
 *   heard of a pause still records nothing.
 *
 * Nothing here touches `localStorage`. The old browser copy
 * (`iris_reading_history`) is only ever wiped, by the auth store, never read.
 */

export interface HistoryItem {
  recordId:  number;
  /** False when the reader can no longer read the Record. */
  available: boolean;
  viewedAt:  string | null;
  record?:   RecordListItem;
}

type LoadState = "idle" | "loading" | "ready" | "error";

interface HistoryState {
  epoch:       number;
  load:        LoadState;
  /** `load` is `error` because the read timed out (IR-906). */
  interrupted: boolean;
  items:       HistoryItem[];
  /** The account's setting; `null` until it has been read this session. */
  keepHistory: boolean | null;
  failure:     string | null;
  /** Read the history and the setting again (My Library does on every visit). */
  refresh:        () => Promise<void>;
  /** Called by the paper view once a Record has loaded. Never throws. */
  recordVisit:    (recordId: number) => Promise<void>;
  clear:          () => Promise<boolean>;
  setKeepHistory: (keep: boolean) => Promise<boolean>;
  dismissFailure: () => void;
}

const empty = () => ({
  load: "idle" as LoadState, interrupted: false, items: [] as HistoryItem[], keepHistory: null, failure: null,
});

function toItem(entry: ReadingHistoryEntry): HistoryItem {
  if (!entry.available) return { recordId: entry.record_id, available: false, viewedAt: null };
  return { recordId: entry.record_id, available: true, viewedAt: entry.viewed_at, record: entry.record };
}

const currentEpoch = () => useAuthStore.getState().sessionEpoch;

export const useHistoryStore = create<HistoryState>()((set, get) => ({
  epoch: currentEpoch(),
  ...empty(),

  refresh: async () => {
    if (!useAuthStore.getState().isAuthenticated) return;
    const epoch = currentEpoch();
    set({ load: "loading", interrupted: false, epoch });
    try {
      const [history, preferences] = await Promise.all([libraryApi.history(), libraryApi.preferences()]);
      if (currentEpoch() !== epoch) return;
      set({
        items: (history.data.results ?? []).map(toItem),
        keepHistory: typeof preferences.data?.keep_history === "boolean" ? preferences.data.keep_history : null,
        load: "ready",
      });
    } catch (error) {
      if (currentEpoch() !== epoch) return;
      set({ load: "error", interrupted: isRequestTimeout(error) });
    }
  },

  recordVisit: async (recordId) => {
    if (!useAuthStore.getState().isAuthenticated) return;
    const epoch = currentEpoch();
    try {
      // Only "kept" is trusted from earlier in the session. A pause is asked
      // again on every paper: resuming on another device never reaches this
      // one otherwise, because nothing would be sent to learn of it. A stale
      // "kept" is harmless, since the server records nothing while paused.
      let keep = get().keepHistory;
      if (keep !== true) {
        const { data } = await libraryApi.preferences();
        if (currentEpoch() !== epoch) return;
        keep = data?.keep_history !== false;
        set({ keepHistory: keep });
      }
      if (!keep) return;
      await libraryApi.visit(recordId);
    } catch {
      /* A missed entry costs nothing; reading the paper must never fail for it. */
    }
  },

  clear: async () => {
    const epoch = currentEpoch();
    const previous = get().items;
    set({ items: [], failure: null });
    try {
      await libraryApi.clearHistory();
      return true;
    } catch {
      if (currentEpoch() !== epoch) return false;
      set({ items: previous, failure: "Could not clear your history. Nothing was removed; try again." });
      return false;
    }
  },

  setKeepHistory: async (keep) => {
    const epoch = currentEpoch();
    const previous = get().keepHistory;
    set({ keepHistory: keep, failure: null });
    try {
      await libraryApi.updatePreferences({ keep_history: keep });
      return true;
    } catch {
      if (currentEpoch() !== epoch) return false;
      set({
        keepHistory: previous,
        failure: keep
          ? "Could not turn history back on. Nothing was changed; try again."
          : "Could not pause your history. Nothing was changed; try again.",
      });
      return false;
    }
  },

  dismissFailure: () => set({ failure: null }),
}));

/** A new session starts with no history and an unread setting (the IR-746 pattern). */
useAuthStore.subscribe((state, previous) => {
  if (state.sessionEpoch !== previous.sessionEpoch) {
    useHistoryStore.setState({ epoch: state.sessionEpoch, ...empty() });
  }
});
