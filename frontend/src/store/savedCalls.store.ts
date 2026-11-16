import { create } from "zustand";

import { opportunitiesApi } from "@/api/opportunities";
import type { Opportunity, SavedCallEntry } from "@/types/opportunities";

import { useAuthStore } from "./auth.store";
import { useUIStore } from "./ui.store";

/**
 * The signed-in reader's saved Calls (IR-766, ADR-050 decision 13; the server
 * side is IR-649). The board's Save control and Saved filter and My Library's
 * Saved calls read this one store, so they never disagree. It behaves as the
 * paper library does (`library.store.ts`, IR-566):
 *
 * - **Cleared on every session change**, so the next person on a shared PC
 *   starts empty.
 * - **Fenced:** an answer that lands after the session changed is dropped.
 * - **Optimistic, with a rollback that says so:** a save or removal shows at
 *   once; if the server refuses, the previous state returns and a toast says
 *   what failed, with Try again (DESIGN.md §Toasts).
 *
 * Nothing here touches the browser's storage. Calls saved in the browser
 * before this are deleted, never imported (`lib/recordLibrary.ts`).
 */

export interface SavedCall {
  callId:    number;
  /** False once the Call is sent back to RDCO or rejected (IR-649): only its id is known. */
  available: boolean;
  savedAt:   string;
  call?:     Opportunity;
}

type LoadState = "idle" | "loading" | "ready" | "error";

interface SavedCallsState {
  epoch: number;
  load:  LoadState;
  items: Record<number, SavedCall>;
  ensureLoaded: (force?: boolean) => Promise<void>;
  isSaved: (callId: number) => boolean;
  /** Saved Calls, newest first; an unavailable one, which has no date, last. */
  sorted: () => SavedCall[];
  save:   (call: Opportunity) => Promise<boolean>;
  /** `title` names the Call in a failure, when the store no longer has it. */
  unsave: (callId: number, title: string) => Promise<boolean>;
}

function toItem(entry: SavedCallEntry): SavedCall {
  return entry.available
    ? { callId: entry.call_id, available: true, savedAt: entry.saved_at, call: entry.call }
    : { callId: entry.call_id, available: false, savedAt: "" };
}

const currentEpoch = () => useAuthStore.getState().sessionEpoch;
const empty = () => ({ load: "idle" as LoadState, items: {} as Record<number, SavedCall> });

/** Per-Call write sequence: only the newest write's answer is applied. */
const writes = new Map<number, number>();
function nextWrite(callId: number): number {
  const n = (writes.get(callId) ?? 0) + 1;
  writes.set(callId, n);
  return n;
}
const isLatest = (callId: number, n: number) => writes.get(callId) === n;

function without(items: Record<number, SavedCall>, callId: number, value?: SavedCall) {
  const next = { ...items };
  if (value) next[callId] = value;
  else delete next[callId];
  return next;
}

let inflightLoad: Promise<void> | null = null;

export const useSavedCallsStore = create<SavedCallsState>()((set, get) => {
  const failed = (message: string, retry: () => void) =>
    useUIStore.getState().addToast({ type: "error", message, action: { label: "Try again", onClick: retry } });

  return {
    epoch: currentEpoch(),
    ...empty(),

    ensureLoaded: async (force = false) => {
      if (!useAuthStore.getState().isAuthenticated) return;
      const { load } = get();
      if (!force && (load === "ready" || load === "loading")) return inflightLoad ?? undefined;

      const epoch = currentEpoch();
      set({ load: "loading", epoch });
      const request = opportunitiesApi.saved().then(
        ({ data }) => {
          if (currentEpoch() !== epoch) return;
          const items: Record<number, SavedCall> = {};
          for (const entry of data?.results ?? []) items[entry.call_id] = toItem(entry);
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

    isSaved: (callId) => get().items[callId] !== undefined,

    sorted: () => Object.values(get().items).sort((a, b) => {
      if (a.available !== b.available) return a.available ? -1 : 1;
      return b.savedAt.localeCompare(a.savedAt);
    }),

    save: async (call) => {
      const epoch = currentEpoch();
      const n = nextWrite(call.id);
      const previous = get().items[call.id];
      set((s) => ({
        items: { ...s.items, [call.id]: { callId: call.id, available: true, savedAt: previous?.savedAt || new Date().toISOString(), call } },
      }));
      try {
        const { data } = await opportunitiesApi.save(call.id);
        if (currentEpoch() !== epoch || !isLatest(call.id, n)) return true;
        set((s) => ({ items: { ...s.items, [call.id]: toItem(data) } }));
        return true;
      } catch {
        if (currentEpoch() !== epoch || !isLatest(call.id, n)) return false;
        set((s) => ({ items: without(s.items, call.id, previous) }));
        failed(`Could not save ${call.title}. Nothing was changed.`, () => void get().save(call));
        return false;
      }
    },

    unsave: async (callId, title) => {
      const epoch = currentEpoch();
      const n = nextWrite(callId);
      const previous = get().items[callId];
      set((s) => ({ items: without(s.items, callId) }));
      try {
        await opportunitiesApi.unsave(callId);
        return true;
      } catch {
        if (currentEpoch() !== epoch || !isLatest(callId, n)) return false;
        set((s) => ({ items: without(s.items, callId, previous) }));
        failed(`Could not remove ${title}. It is still saved.`, () => void get().unsave(callId, title));
        return false;
      }
    },
  };
});

/** A new session starts with no saved Calls (the IR-746 pattern, as `library.store.ts`). */
useAuthStore.subscribe((state, previous) => {
  if (state.sessionEpoch !== previous.sessionEpoch) {
    writes.clear();
    inflightLoad = null;
    useSavedCallsStore.setState({ epoch: state.sessionEpoch, ...empty() });
  }
});
