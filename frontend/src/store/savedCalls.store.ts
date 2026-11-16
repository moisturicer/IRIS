import { create } from "zustand";

import { opportunitiesApi } from "@/api/opportunities";
import { isRequestTimeout } from "@/api/requestPolicy";
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
 * - **Fenced:** an answer, or a toast's Try again, from before the session
 *   changed is ignored.
 * - **Optimistic, with a rollback that says so:** a save or removal shows at
 *   once; if the server refuses, the previous state returns and a toast says
 *   what failed, with Try again (DESIGN.md §Toasts).
 * - **A timed-out read is "interrupted"**, as the library's is (IR-906).
 *
 * Nothing here touches the browser's storage. Calls saved in the browser
 * before this are deleted, never imported (`lib/recordLibrary.ts`).
 */

/**
 * One saved Call, in the API's two shapes: a confirmed Call whole, or one
 * sent back to RDCO or rejected, of which only the id is known (IR-649).
 */
export type SavedCall =
  | { callId: number; available: true; savedAt: string; call: Opportunity }
  | { callId: number; available: false };

type LoadState = "idle" | "loading" | "ready" | "error";

interface SavedCallsState {
  epoch: number;
  load:  LoadState;
  /** `load` is `error` because the read timed out, not because it was refused. */
  interrupted: boolean;
  items: Record<number, SavedCall>;
  /** The saved Call ids, newest first, as the server orders them; a new save goes first. */
  order: number[];
  ensureLoaded: (force?: boolean) => Promise<void>;
  save:   (call: Opportunity) => Promise<boolean>;
  unsave: (call: Pick<Opportunity, "id" | "title">) => Promise<boolean>;
}

function toItem(entry: SavedCallEntry): SavedCall {
  return entry.available
    ? { callId: entry.call_id, available: true, savedAt: entry.saved_at, call: entry.call }
    : { callId: entry.call_id, available: false };
}

const currentEpoch = () => useAuthStore.getState().sessionEpoch;
const empty = () => ({ load: "idle" as LoadState, interrupted: false, items: {} as Record<number, SavedCall>, order: [] as number[] });

/** Per-Call write sequence: only the newest write's answer is applied. */
const writes = new Map<number, number>();
function nextWrite(callId: number): number {
  const n = (writes.get(callId) ?? 0) + 1;
  writes.set(callId, n);
  return n;
}
const isLatest = (callId: number, n: number) => writes.get(callId) === n;

/** `items` with `callId` set back to `value`, or taken out when there is none. */
function restore(items: Record<number, SavedCall>, callId: number, value: SavedCall | undefined) {
  const next = { ...items };
  if (value) next[callId] = value;
  else delete next[callId];
  return next;
}

let inflightLoad: Promise<void> | null = null;

export const useSavedCallsStore = create<SavedCallsState>()((set, get) => {
  /** A toast for a failed write. Its Try again does nothing once the session changed. */
  const failed = (message: string, epoch: number, retry: () => void) =>
    useUIStore.getState().addToast({
      type: "error", message,
      action: { label: "Try again", onClick: () => { if (currentEpoch() === epoch) retry(); } },
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
      const request = opportunitiesApi.saved().then(
        ({ data }) => {
          if (currentEpoch() !== epoch) return;
          const entries = Array.isArray(data?.results) ? data.results : [];
          const items: Record<number, SavedCall> = {};
          for (const entry of entries) items[entry.call_id] = toItem(entry);
          set({ items, order: entries.map((e) => e.call_id), load: "ready" });
        },
        (error: unknown) => {
          if (currentEpoch() !== epoch) return;
          set({ load: "error", interrupted: isRequestTimeout(error) });
        },
      );
      inflightLoad = request.finally(() => { inflightLoad = null; });
      return inflightLoad;
    },

    save: async (call) => {
      const epoch = currentEpoch();
      const n = nextWrite(call.id);
      const previous = get().items[call.id];
      const previousOrder = get().order;
      set((s) => ({
        items: { ...s.items, [call.id]: { callId: call.id, available: true, savedAt: new Date().toISOString(), call } },
        order: previous ? s.order : [call.id, ...s.order],
      }));
      try {
        const { data } = await opportunitiesApi.save(call.id);
        if (currentEpoch() !== epoch || !isLatest(call.id, n)) return true;
        set((s) => ({ items: { ...s.items, [call.id]: toItem(data) } }));
        return true;
      } catch {
        if (currentEpoch() !== epoch || !isLatest(call.id, n)) return false;
        set((s) => ({ items: restore(s.items, call.id, previous), order: previousOrder }));
        failed(`Could not save ${call.title}. Nothing was changed.`, epoch, () => void get().save(call));
        return false;
      }
    },

    unsave: async (call) => {
      const epoch = currentEpoch();
      const n = nextWrite(call.id);
      const previous = get().items[call.id];
      const previousOrder = get().order;
      set((s) => ({ items: restore(s.items, call.id, undefined), order: s.order.filter((id) => id !== call.id) }));
      try {
        await opportunitiesApi.unsave(call.id);
        return true;
      } catch {
        if (currentEpoch() !== epoch || !isLatest(call.id, n)) return false;
        set((s) => ({ items: restore(s.items, call.id, previous), order: previousOrder }));
        failed(`Could not remove ${call.title}. It is still saved.`, epoch, () => void get().unsave(call));
        return false;
      }
    },
  };
});

/** Saved Calls, newest first, as the server orders them (ADR-050 decision 13). */
export function savedInOrder(items: Record<number, SavedCall>, order: number[]): SavedCall[] {
  return order.flatMap((id) => (items[id] ? [items[id]] : []));
}

/** A new session starts with no saved Calls (the IR-746 pattern, as `library.store.ts`). */
useAuthStore.subscribe((state, previous) => {
  if (state.sessionEpoch !== previous.sessionEpoch) {
    writes.clear();
    inflightLoad = null;
    useSavedCallsStore.setState({ epoch: state.sessionEpoch, ...empty() });
  }
});
