import { create } from "zustand";

import type { TourKey } from "./tourKeys";

/**
 * Which student tour is running, and which this session has marked (IR-1342).
 *
 * One tour at a time: a tour starts only while `active` is empty. `marked`
 * remembers the tours this browser session has marked seen, whether or not the
 * server heard it, so a failed request or a fresh `/users/me/` read can never
 * replay a tour on every navigation.
 */
interface TourSession {
  active: TourKey | null;
  marked: ReadonlySet<TourKey>;
  start: (key: TourKey) => boolean;
  stop: (key: TourKey) => void;
  mark: (key: TourKey) => void;
  /** Tests only: back to a fresh session. */
  reset: () => void;
}

export const useTourSession = create<TourSession>((set, get) => ({
  active: null,
  marked: new Set(),
  start: (key) => {
    if (get().active !== null) return false;
    set({ active: key });
    return true;
  },
  stop: (key) => {
    if (get().active === key) set({ active: null });
  },
  mark: (key) => {
    if (get().marked.has(key)) return;
    set({ marked: new Set([...get().marked, key]) });
  },
  reset: () => set({ active: null, marked: new Set() }),
}));
