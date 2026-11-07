import { create } from "zustand";

import { libraryApi, type FeedQuery, type SavedFeed } from "@/api/library";
import { isRequestTimeout } from "@/api/requestPolicy";

import { useAuthStore } from "./auth.store";

/**
 * The signed-in reader's saved custom feeds (IR-577).
 *
 * One store, so Discover's menu and the open feed always agree. It belongs to
 * one session, the way `library.store` does:
 *
 * - **Cleared on every session change.** `sessionEpoch` moves on sign-in,
 *   sign-out and session end, so the next person on a shared PC starts empty.
 * - **Fenced.** A response that lands after the epoch moved is dropped, never
 *   shown to the next account.
 * - **Written with the server's say-so.** Unlike a save, a feed can be refused
 *   for reasons the reader has to read (the limit, a duplicate name, empty
 *   criteria), so nothing is shown before the server accepts it, and a refusal
 *   comes back as a message for the form to keep on screen.
 *
 * Nothing here touches `localStorage`.
 */

type LoadState = "idle" | "loading" | "ready" | "error";

export type FeedResult = { ok: true; feed: SavedFeed } | { ok: false; message: string };
export type RemoveResult = { ok: true } | { ok: false; message: string };

interface FeedsState {
  /** The epoch these feeds were loaded in; anything else is another session's. */
  epoch:       number;
  load:        LoadState;
  /** `load` is `error` because the read timed out, not because it was refused. */
  interrupted: boolean;
  feeds:       SavedFeed[];
  /** How many feeds an account may keep, as the server reports it. */
  limit:       number;

  ensureLoaded: (force?: boolean) => Promise<void>;
  create: (name: string, query: FeedQuery) => Promise<FeedResult>;
  /** Rename it, replace its criteria, or both. */
  update: (id: number, change: { name?: string; query?: FeedQuery }) => Promise<FeedResult>;
  remove: (id: number) => Promise<RemoveResult>;
}

const currentEpoch = () => useAuthStore.getState().sessionEpoch;
const empty = () => ({ load: "idle" as LoadState, interrupted: false, feeds: [] as SavedFeed[] });

const SIGNED_OUT = "You were signed out before this finished. Nothing was changed.";

/**
 * The server's own reason for a refusal: `detail` (the limit), else the first
 * message on the field it names. Anything else is the fallback, so a lost
 * connection never shows a stranger's wording.
 */
function reasonFrom(error: unknown, fallback: string): string {
  const data = (error as { response?: { data?: Record<string, unknown> } } | null)?.response?.data;
  if (data && typeof data === "object") {
    if (typeof data.detail === "string") return data.detail;
    for (const field of ["name", "query", "detail"]) {
      const messages = data[field];
      if (Array.isArray(messages) && typeof messages[0] === "string") return messages[0];
    }
  }
  return fallback;
}

let inflightLoad: Promise<void> | null = null;

export const useFeedsStore = create<FeedsState>()((set, get) => ({
  epoch: currentEpoch(),
  limit: 10,
  ...empty(),

  ensureLoaded: async (force = false) => {
    if (!useAuthStore.getState().isAuthenticated) return;
    const { load } = get();
    if (!force && (load === "ready" || load === "loading")) return inflightLoad ?? undefined;

    const epoch = currentEpoch();
    set({ load: "loading", interrupted: false, epoch });
    const request = libraryApi.feeds().then(
      ({ data }) => {
        if (currentEpoch() !== epoch) return;
        set({ feeds: data.results ?? [], limit: data.limit, load: "ready" });
      },
      (error: unknown) => {
        if (currentEpoch() !== epoch) return;
        set({ load: "error", interrupted: isRequestTimeout(error) });
      },
    );
    inflightLoad = request.finally(() => { inflightLoad = null; });
    return inflightLoad;
  },

  create: async (name, query) => {
    const epoch = currentEpoch();
    try {
      const { data } = await libraryApi.createFeed({ name, query });
      if (currentEpoch() !== epoch) return { ok: false, message: SIGNED_OUT };
      set((s) => ({ feeds: [...s.feeds, data] }));
      return { ok: true, feed: data };
    } catch (error) {
      return { ok: false, message: reasonFrom(error, "The feed could not save. Nothing was changed; try again.") };
    }
  },

  update: async (id, change) => {
    const epoch = currentEpoch();
    try {
      const { data } = await libraryApi.updateFeed(id, change);
      if (currentEpoch() !== epoch) return { ok: false, message: SIGNED_OUT };
      set((s) => ({ feeds: s.feeds.map((f) => (f.id === id ? data : f)) }));
      return { ok: true, feed: data };
    } catch (error) {
      return { ok: false, message: reasonFrom(error, "The feed could not save. Nothing was changed; try again.") };
    }
  },

  remove: async (id) => {
    const epoch = currentEpoch();
    try {
      await libraryApi.deleteFeed(id);
      if (currentEpoch() !== epoch) return { ok: false, message: SIGNED_OUT };
      set((s) => ({ feeds: s.feeds.filter((f) => f.id !== id) }));
      return { ok: true };
    } catch (error) {
      return { ok: false, message: reasonFrom(error, "The feed could not be deleted. It is still saved; try again.") };
    }
  },
}));

/**
 * A new session starts with no feeds. Subscribing here keeps the auth store
 * from having to know this one exists (the IR-746 pattern).
 */
useAuthStore.subscribe((state, previous) => {
  if (state.sessionEpoch !== previous.sessionEpoch) {
    inflightLoad = null;
    useFeedsStore.setState({ epoch: state.sessionEpoch, ...empty() });
  }
});
